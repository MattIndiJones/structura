"""Jeu d'évaluation de l'assistant de scripting.

Mesure ce que le prompt obtient réellement d'un modèle donné, sur des demandes
en français dont on connaît les propriétés STRUCTURELLES attendues — pas le
texte attendu : deux scripts corrects peuvent s'écrire différemment, ce qui se
vérifie c'est qu'ils décrivent le bon produit.

Deux usages :

1. **Choisir le modèle local.** C'est ce qui départage qwen2.5-coder:14b,
   llama3.3:70b et les autres, sur des chiffres plutôt que sur une intuition.
2. **Protéger le prompt.** Toute retouche du prompt système peut améliorer un
   cas et en casser trois ; sans mesure, la dégradation est invisible.

N'est PAS un test pytest : il appelle un modèle, donc il est lent, non
déterministe et dépend d'un service externe. Il se lance à la main.

Usage :
    .venv\\Scripts\\python.exe backend\\scripts\\eval_script_assistant.py
    .venv\\Scripts\\python.exe backend\\scripts\\eval_script_assistant.py --model mistral:latest
    .venv\\Scripts\\python.exe backend\\scripts\\eval_script_assistant.py --provider anthropic
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.services.llm import generate, LlmError          # noqa: E402
from backend.app.services.llm.providers import PROVIDERS         # noqa: E402

UL = [dict(name="S1", ticker="", ccy="EUR", sigma=0.20, q=0.02, v0=0.04,
           kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70, alpha=0.20, beta=1.0,
           rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]


def _has(pattern):
    return lambda out: bool(re.search(pattern, out["script"], re.I | re.M))


def _n_dates(n):
    def check(out):
        dates = re.findall(r"^\s*AT\s+([\d.,\s]+)\s*:?\s*$", out["script"], re.M)
        if not dates:
            return False
        return len([d for d in dates[0].split(",") if d.strip()]) == n
    return check


# (nom, demande en français, [(libellé du critère, prédicat)])
CASES = [
    ("autocall simple",
     "un autocall 3 ans, observation annuelle, rappel si le sous-jacent est au-dessus "
     "de 100% de son niveau initial, coupon 8% par an cumulé, capital protégé au-dessus "
     "de 60% constaté à maturité",
     [("compile", lambda o: o["ok"]),
      ("STOP présent", lambda o: o["has_stop"]),
      ("3 dates d'observation", _n_dates(3)),
      ("bloc de maturité", _has(r"^AT\s+MATURITY")),
      ("price au pair", lambda o: o["price_pct"] and 55 < o["price_pct"] < 165)]),

    ("barrière américaine",
     "un reverse convertible 2 ans, coupon 9% fixe versé chaque année, capital remboursé "
     "au pair sauf si le sous-jacent passe sous 65% à un moment quelconque de la vie du "
     "produit — la barrière est observée en continu",
     [("compile", lambda o: o["ok"]),
      ("utilise WOF_MIN", _has(r"\bWOF_MIN\b")),
      ("bloc de maturité", _has(r"^AT\s+MATURITY")),
      ("price au pair", lambda o: o["price_pct"] and 55 < o["price_pct"] < 165)]),

    ("coupon à mémoire",
     "un phoenix 3 ans, coupon 8% par an versé si le sous-jacent est au-dessus de 70%, "
     "avec effet mémoire : les coupons non versés sont rattrapés dès qu'une constatation "
     "repasse au-dessus. Rappel si le sous-jacent dépasse 100%.",
     [("compile", lambda o: o["ok"]),
      ("STOP présent", lambda o: o["has_stop"]),
      ("mémoire mise à jour", _has(r"SET\s+\w*MEMO\w*\s*=")),
      ("price au pair", lambda o: o["price_pct"] and 55 < o["price_pct"] < 165)]),

    ("option vanille",
     "un simple call européen 1 an de strike 100%, sans nominal remboursé",
     [("compile", lambda o: o["ok"]),
      ("pas de rappel", lambda o: not o["has_stop"]),
      ("utilise MAX", _has(r"\bMAX\s*\(")),
      ("prix d'option", lambda o: o["price_pct"] is not None and 0 < o["price_pct"] < 40)]),

    ("worst-of 2 actifs",
     "un autocall 2 ans sur un panier de 2 actions, observation semestrielle, rappel si "
     "la moins performante des deux est au-dessus de 100%, coupon 10% par an cumulé, "
     "protection du capital à 60% à maturité",
     [("compile", lambda o: o["ok"]),
      ("STOP présent", lambda o: o["has_stop"]),
      ("worst-of", _has(r"\bWOF\b")),
      ("4 observations", _n_dates(4))]),

    ("capital garanti",
     "un produit 5 ans à capital garanti à 100%, avec une participation de 60% à la "
     "hausse du sous-jacent au-delà de son niveau initial",
     [("compile", lambda o: o["ok"]),
      ("bloc de maturité", _has(r"^AT\s+MATURITY")),
      ("participation via MAX", _has(r"\bMAX\s*\(")),
      ("price au-dessus du plancher",
       lambda o: o["price_pct"] is not None and o["price_pct"] > 80)]),
]


def run(provider: str, model: str | None, cases=CASES) -> int:
    label = model or PROVIDERS[provider].default_model
    print(f"\n{'=' * 74}\nJeu d'évaluation — {provider} / {label}\n{'=' * 74}")
    total = passed = 0
    t0 = time.time()

    for nom, demande, criteres in cases:
        try:
            out = generate(demande, provider=provider, model=model,
                           underlyings=UL, corr=[[1.0]], r=0.025, T=3.0)
        except LlmError as e:
            print(f"\n  {nom:<22} ÉCHEC MOTEUR : {str(e)[:90]}")
            total += len(criteres)
            continue

        res = []
        for libelle, pred in criteres:
            try:
                ok = bool(pred(out))
            except Exception:
                ok = False
            res.append((libelle, ok))
            total += 1
            passed += ok

        score = sum(1 for _, ok in res if ok)
        print(f"\n  {nom:<22} {score}/{len(res)}   "
              f"({out['elapsed_ms'] / 1000:.0f} s, {out['repairs']} réparation(s))")
        for libelle, ok in res:
            print(f"      {'✓' if ok else '✗'} {libelle}")
        if not out["ok"]:
            print(f"      parser : {(out['parse_error'] or '')[:110]}")
        alertes = [c for c in out["checks"] if c["level"] == "attention"]
        for c in alertes:
            print(f"      ⚠ {c['label']} — {c['detail'][:90]}")

    pct = 100 * passed / total if total else 0
    print(f"\n{'-' * 74}\nTOTAL {passed}/{total} critères ({pct:.0f} %) "
          f"en {time.time() - t0:.0f} s\n")
    return 0 if pct >= 70 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider", default="ollama", choices=list(PROVIDERS))
    ap.add_argument("--model", default=None,
                    help="par défaut : le modèle par défaut du fournisseur")
    ap.add_argument("--case", default=None,
                    help="n'exécuter qu'un cas (sous-chaîne de son nom)")
    a = ap.parse_args()
    cases = CASES
    if a.case:
        cases = [c for c in CASES if a.case.lower() in c[0].lower()]
        if not cases:
            print(f"aucun cas ne correspond à {a.case!r}")
            return 2
    return run(a.provider, a.model, cases)


if __name__ == "__main__":
    sys.exit(main())
