"""Assainissement et contrôle d'un script produit par un modèle.

Le parser attrape les scripts qui ne compilent pas. Il n'attrape pas le cas
dangereux : un script qui compile, price, et décrit un AUTRE produit que celui
demandé. Un `STOP` oublié fait un autocall qui ne rappelle jamais ; un `WOF` à
la place d'un `WOF_MIN` transforme une barrière américaine en européenne, ce qui
vaut plusieurs points de nominal. Aucun des deux ne lève quoi que ce soit.

Ce module produit donc une fiche de contrôle. Elle ne bloque rien : elle rend
visible ce que le script fait vraiment, pour que la relecture humaine porte sur
des points précis au lieu d'être une relecture de code.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ...core.payscript.parser import parse_script, CompiledScript
from .prompt import SCRIPT_MARK, EXPLAIN_MARK

# Sévérités : 'ok' (vert), 'attention' (orange, à regarder), 'info' (neutre).
OK, WARN, INFO = "ok", "attention", "info"


@dataclass
class Check:
    label: str
    level: str
    detail: str = ""


@dataclass
class Validation:
    script: str
    explanation: str
    ok: bool
    checks: list[Check] = field(default_factory=list)
    parse_error: str | None = None
    params: list[dict] = field(default_factory=list)
    n_events: int = 0
    has_stop: bool = False
    price_pct: float | None = None
    price_error: str | None = None
    proba: dict | None = None

    def as_dict(self) -> dict:
        return {
            "script": self.script,
            "explanation": self.explanation,
            "ok": self.ok,
            "parse_error": self.parse_error,
            "checks": [c.__dict__ for c in self.checks],
            "params": self.params,
            "n_events": self.n_events,
            "has_stop": self.has_stop,
            "price_pct": self.price_pct,
            "price_error": self.price_error,
            "proba": self.proba,
        }


# ── 1. Assainissement ───────────────────────────────────────────────

def split_response(raw: str) -> tuple[str, str]:
    """Sépare script et explication.

    Les modèles encadrent le code de balises markdown et ajoutent de la prose
    malgré la consigne — systématiquement, tous fournisseurs confondus. On
    nettoie plutôt que de refuser : refuser ferait échouer un script correct
    pour une décoration."""
    text = (raw or "").replace("\r\n", "\n").strip()

    script, explanation = text, ""
    if SCRIPT_MARK in text:
        after = text.split(SCRIPT_MARK, 1)[1]
        if EXPLAIN_MARK in after:
            script, explanation = after.split(EXPLAIN_MARK, 1)
        else:
            script = after
    elif EXPLAIN_MARK in text:
        script, explanation = text.split(EXPLAIN_MARK, 1)

    script = _strip_fences(script)
    return script.strip(), explanation.strip()


def _strip_fences(s: str) -> str:
    """Retire les blocs ```…``` et la prose autour."""
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", s, re.S)
    if blocks:
        # Le bloc le plus long est le script ; les autres sont des extraits.
        return max(blocks, key=len)
    # Pas de balises : on écarte les lignes de prose avant la première
    # instruction PayScript reconnaissable.
    lines = s.split("\n")
    start = 0
    for i, line in enumerate(lines):
        if re.match(r"^\s*(PARAM|CONSTAT|SET|AT|#)", line, re.I):
            start = i
            break
    return "\n".join(lines[start:])


# ── 2. Contrôles structurels ────────────────────────────────────────

_RECALL_WORDS = ("autocall", "rappel", "rappelable", "callable", "remboursement anticipé",
                 "remboursement anticipe", "athena", "phoenix")
_BARRIER_WORDS = ("barrière", "barriere", "knock", "ki ", "pdi", "protection",
                  "capital garanti", "capital protégé", "capital protege")
_MEMORY_WORDS = ("mémoire", "memoire", "rattrapage", "cumulé", "cumule")
_AMERICAN_WORDS = ("continu", "à tout moment", "a tout moment", "américaine",
                   "americaine", "franchi", "touché", "touche", "daily", "quotidien")


def structural_checks(compiled: CompiledScript, script: str,
                      description: str, n_underlyings: int) -> list[Check]:
    """La fiche de contrôle. Chaque ligne répond à « le script fait-il ce que
    la demande dit ? », jamais à « le script compile-t-il ? »."""
    d = (description or "").lower()
    checks: list[Check] = []

    # -- Le produit se solde-t-il ?
    has_mat = any(e.type == "AT_MATURITY" for e in compiled.events)
    checks.append(Check(
        "Bloc de maturité", OK if has_mat else WARN,
        "Présent." if has_mat else
        "ABSENT — une trajectoire jamais rappelée ne paie rien."))

    # -- Rappel demandé vs rappel écrit
    veut_rappel = any(m in d for m in _RECALL_WORDS)
    if veut_rappel or compiled.has_stop:
        coherent = veut_rappel == compiled.has_stop
        checks.append(Check(
            "Rappel anticipé", OK if coherent else WARN,
            "STOP présent, cohérent avec la demande." if coherent and veut_rappel
            else "STOP présent (non demandé explicitement)." if compiled.has_stop
            else "La demande décrit un rappel mais le script ne contient AUCUN "
                 "STOP : le produit continuera d'observer après le rappel."))

    # -- Barrière : européenne ou américaine ?
    if any(m in d for m in _BARRIER_WORDS):
        use_min = bool(re.search(r"\bWOF_MIN\b|\bS_MIN\[", script, re.I))
        use_spot = bool(re.search(r"\bWOF\b(?!_MIN)", script, re.I))
        veut_americaine = any(m in d for m in _AMERICAN_WORDS)
        if use_min and not use_spot:
            nature = "américaine (WOF_MIN) — franchissement à tout moment"
        elif use_min and use_spot:
            nature = "mixte : WOF pour certaines conditions, WOF_MIN pour d'autres"
        else:
            nature = "européenne (WOF) — observée uniquement aux dates de constatation"
        niveau = WARN if (veut_americaine and not use_min) else INFO
        checks.append(Check(
            "Nature de la barrière", niveau,
            f"Retenue : {nature}."
            + (" La demande évoque un franchissement en continu : WOF_MIN était "
               "probablement attendu." if niveau == WARN else "")))

    # -- Coupon à mémoire
    if any(m in d for m in _MEMORY_WORDS):
        a_memo = bool(re.search(r"SET\s+\w*MEMO\w*\s*=", script, re.I))
        checks.append(Check(
            "Coupon à mémoire", OK if a_memo else WARN,
            "Mémoire mise à jour après versement." if a_memo else
            "Aucune variable de mémoire mise à jour : les coupons manqués ne "
            "seront jamais rattrapés."))

    # -- Sous-jacents référencés
    idx = {int(m) for m in re.findall(r"S(?:_MIN|_MAX|_PREV)?\[(\d+)\]", script)}
    if idx:
        hors = sorted(i for i in idx if not 1 <= i <= n_underlyings)
        checks.append(Check(
            "Sous-jacents référencés", WARN if hors else OK,
            f"Indices hors du panier configuré ({n_underlyings} actif(s)) : {hors}."
            if hors else f"Indices {sorted(idx)} cohérents avec {n_underlyings} actif(s)."))

    # -- Paramètres déclarés mais jamais lus
    corps = "\n".join(l for l in script.split("\n")
                      if not re.match(r"^\s*PARAM", l, re.I))
    inutiles = [p.name for p in compiled.params
                if not re.search(rf"\b{re.escape(p.name)}\b", corps, re.I)]
    if inutiles:
        checks.append(Check(
            "Paramètres inutilisés", WARN,
            f"Déclarés mais jamais lus : {', '.join(inutiles)} — l'interface "
            f"affichera un champ sans effet sur le prix."))

    # -- Dates d'observation
    dates = sorted({d_ for e in compiled.events if e.type == "AT" for d_ in e.dates})
    if dates:
        checks.append(Check(
            "Dates d'observation", INFO,
            f"{len(dates)} date(s) : {', '.join(f'{x:g}' for x in dates[:12])}"
            + ("…" if len(dates) > 12 else "") + " (années)."))
    elif any(e.constat_ref for e in compiled.events):
        checks.append(Check("Dates d'observation", INFO,
                            "Calendrier CONSTAT — à renseigner dans l'interface."))

    return checks


# ── 3. Pricing de contrôle ──────────────────────────────────────────

def smoke_price(compiled: CompiledScript, underlyings, corr, r: float,
                T: float, user_params: dict) -> tuple[float | None, str | None, dict | None]:
    """Le script tourne-t-il, et sort-il un nombre défendable ?

    Ce n'est pas un pricing : c'est un test de vie. Un script qui compile peut
    encore mourir à l'exécution (indice hors bornes, division par zéro) ou
    sortir 340 % — auquel cas il dit quelque chose."""
    from ...core.payscript.engine import run_mc, run_mc_proba
    from ...core.payscript.parser import effective_T_max
    try:
        T_eff = effective_T_max(compiled, T)
        res = run_mc(compiled, underlyings, corr, r=r, T_max=T_eff, N=2000,
                     model="constant", seed=7, user_params=user_params)
        prix = res["price"] * 100
        if not math.isfinite(prix):
            return None, "Le pricing de contrôle sort une valeur non finie.", None
        proba = None
        try:
            p = run_mc_proba(compiled, underlyings, corr, r=r, T_max=T_eff,
                             N=2000, model="constant", seed=7,
                             user_params=user_params)
            proba = {"autocall_pct": p["autocall_pct"], "ki_pct": p["ki_pct"],
                     "expected_life": p["expected_life"],
                     "capital_loss_pct": p["capital_loss_pct"]}
        except Exception:
            pass                      # diagnostic secondaire, jamais bloquant
        return prix, None, proba
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", None


def price_check(prix: float | None, err: str | None, *, note_like: bool) -> Check:
    """`note_like` : le produit rembourse-t-il un nominal (note, autocall,
    capital garanti) plutôt que de coter une prime (option) ?

    La distinction porte tout le contrôle. Une option vaut légitimement 12 % du
    nominal ; une note structurée à 238 % n'existe pas — c'est la signature d'un
    nominal payé plusieurs fois, typiquement un `STOP` oublié qui laisse le
    produit encaisser à chaque observation ET à maturité."""
    if err:
        return Check("Pricing de contrôle", WARN,
                     f"Le script compile mais ne price pas — {err}")
    if prix is None:
        return Check("Pricing de contrôle", WARN, "Pas de prix.")
    suffixe = " (2 000 chemins, paramètres par défaut)."
    if not -50.0 < prix < 400.0:
        return Check("Pricing de contrôle", WARN,
                     f"{prix:.2f} % du nominal — hors de toute plausibilité, "
                     f"le payoff est probablement mal échelonné.")
    if note_like and not 55.0 <= prix <= 165.0:
        return Check("Pricing de contrôle", WARN,
                     f"{prix:.2f} % du nominal{suffixe} Un produit à nominal "
                     f"remboursé se cote autour du pair : cet écart signale "
                     f"généralement un nominal versé plusieurs fois (STOP "
                     f"manquant) ou un flux à la mauvaise échelle.")
    return Check("Pricing de contrôle", OK, f"{prix:.2f} % du nominal{suffixe}")


def _looks_like_a_note(compiled: CompiledScript, script: str, description: str) -> bool:
    """Une note rembourse un nominal ; une option cote une prime. On le déduit
    du script (un `PAY` du nominal entier) et non de la demande, qui peut être
    muette là-dessus."""
    d = (description or "").lower()
    # Frontières de mots obligatoires : en simple sous-chaîne, « call » se
    # trouve dans « autocall » et classait tout autocall comme une option —
    # exactement le produit dont le contrôle de pair a le plus besoin.
    if re.search(r"\b(option|call|put|spread|digital|vanille|binaire)\b", d):
        return False
    if compiled.has_stop:
        return True
    # `PAY 1`, `PAY ... * 1`, `PAY 1 + ...` : le nominal est remboursé.
    return bool(re.search(r"^\s*PAY\s+(1\b|.*\*\s*1\b|\(1\s*-)", script, re.M | re.I))


# ── 4. Enchaînement complet ─────────────────────────────────────────

def validate(raw_response: str, *, description: str, underlyings, corr,
             r: float, T: float, user_params: dict) -> Validation:
    """Assainit, parse, contrôle. Ne lève pas : un échec est un résultat à
    afficher, pas une exception à avaler."""
    script, explanation = split_response(raw_response)
    v = Validation(script=script, explanation=explanation, ok=False)

    if not script.strip():
        v.parse_error = "Le modèle n'a produit aucun script exploitable."
        return v

    try:
        compiled = parse_script(script)
    except ValueError as e:
        v.parse_error = str(e)
        return v

    v.ok = True
    v.n_events = len(compiled.events)
    v.has_stop = compiled.has_stop
    v.params = [{"name": p.name, "raw_default": p.raw_default,
                 "is_pct": p.is_pct, "desc": p.desc, "kind": p.kind}
                for p in compiled.params]
    v.checks = structural_checks(compiled, script, description, len(underlyings))

    # Un script à CONSTAT non résolus ne peut pas être pricé hors interface.
    if any(e.constat_ref for e in compiled.events):
        v.checks.append(Check(
            "Pricing de contrôle", INFO,
            "Non exécuté : le script référence un calendrier CONSTAT dont les "
            "dates se renseignent dans l'interface."))
        return v

    prix, err, proba = smoke_price(compiled, underlyings, corr, r, T, user_params)
    v.price_pct, v.price_error, v.proba = prix, err, proba
    v.checks.append(price_check(
        prix, err, note_like=_looks_like_a_note(compiled, script, description)))
    return v
