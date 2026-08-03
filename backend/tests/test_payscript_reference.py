"""La référence de langage ne doit jamais mentir sur le langage.

`docs/PAYSCRIPT_REFERENCE.md` a deux lecteurs : l'utilisateur, et le modèle de
l'assistant IA — c'est le corps de son prompt système. Une référence qui dérive
du parser ne se voit pas : le modèle produit alors des scripts syntaxiquement
conformes à une grammaire qui n'existe plus, et l'assistant échoue à chaque
appel sans que rien n'explique pourquoi.

Ce test rend la dérive impossible : un mot ajouté au langage sans documentation,
ou documenté sans exister, fait échouer la suite.
"""
import re
from pathlib import Path

import pytest

from backend.app.core.payscript.parser import (
    language_vocabulary, parse_script,
    MARKET_VARS, FUNCTIONS, INDEXED_VARS, LOGIC_KEYWORDS,
    TOP_LEVEL_STATEMENTS, BODY_STATEMENTS, BASKET_KEYWORD,
)

REFERENCE = Path(__file__).resolve().parents[2] / "docs" / "PAYSCRIPT_REFERENCE.md"


def _documented_vocabulary() -> set[str]:
    """Les noms documentés, lus entre les balises VOCABULAIRE — premier champ
    entre accents graves de chaque ligne de tableau. Délimiter la zone plutôt
    que de ratisser tout le document évite qu'un identifiant cité en prose ou
    dans un exemple compte comme une entrée de vocabulaire."""
    text = REFERENCE.read_text(encoding="utf-8")
    m = re.search(r"<!-- VOCABULAIRE:DEBUT -->(.*?)<!-- VOCABULAIRE:FIN -->", text, re.S)
    assert m, "balises VOCABULAIRE:DEBUT / VOCABULAIRE:FIN absentes de la référence"
    noms = set()
    for line in m.group(1).splitlines():
        row = re.match(r"^\|\s*`([^`]+)`\s*\|", line.strip())
        if row:
            noms.add(row.group(1))
    return noms


def _real_vocabulary() -> set[str]:
    vocab = language_vocabulary()
    return {mot for groupe in vocab.values() for mot in groupe}


def test_la_reference_existe_et_est_lisible():
    assert REFERENCE.exists(), f"référence de langage absente : {REFERENCE}"
    assert len(REFERENCE.read_text(encoding="utf-8")) > 2000


def test_tout_mot_du_langage_est_documente():
    """Sens 1 : le parser ne doit rien accepter que la référence ignore."""
    manquants = _real_vocabulary() - _documented_vocabulary()
    assert not manquants, (
        f"mots acceptés par le parser mais absents de la référence : "
        f"{sorted(manquants)} — le prompt de l'assistant ne les proposera jamais.")


def test_la_reference_n_invente_rien():
    """Sens 2 : la référence ne doit rien promettre que le parser refuse.
    C'est le sens dangereux — il fait écrire au modèle une syntaxe invalide."""
    inventes = _documented_vocabulary() - _real_vocabulary()
    assert not inventes, (
        f"mots documentés mais inconnus du parser : {sorted(inventes)} — "
        f"le modèle les écrira et le script ne parsera pas.")


def test_le_vocabulaire_couvre_les_categories_attendues():
    """Garde-fou sur la structure elle-même : si une catégorie disparaît de
    language_vocabulary(), les deux tests ci-dessus passent au vert en ne
    vérifiant plus rien."""
    vocab = language_vocabulary()
    assert set(vocab) == {"market", "indexed", "functions", "basket",
                          "logic", "top_level", "body"}
    assert all(vocab[k] for k in vocab), "catégorie de vocabulaire vide"
    # Les mots dont dépendent les pièges documentés au §5 doivent exister.
    for essentiel in ("WOF", "WOF_MIN", "INDEX", "INDIC", "STOP", "AT MATURITY", "PAY"):
        assert essentiel in _real_vocabulary()


def test_les_tables_du_module_alimentent_vraiment_le_transpileur():
    """Les tables ont été remontées de _transpile_expr au niveau module. Si
    quelqu'un les remet en dur dans la fonction, le vocabulaire publié cesse de
    décrire le langage réel sans qu'aucun autre test ne bronche."""
    import inspect
    from backend.app.core.payscript import parser as P
    src = inspect.getsource(P._transpile_expr)
    assert "MARKET_VARS" in src and "FUNCTIONS" in src, (
        "_transpile_expr n'utilise plus les tables de vocabulaire du module — "
        "la référence et le prompt décriraient une grammaire fantôme.")
    assert "BASKET_KEYWORD" in src


def test_un_param_ne_peut_pas_porter_un_nom_du_langage():
    """`PARAM FLOOR = 100%` compilait, puis mourait au pricing sur
    `unsupported operand type(s) for +: 'builtin_function_or_method' and 'float'` :
    le transpileur résout FLOOR en priorité comme la fonction. Le template
    « Booster 3Y » livré dans l'éditeur portait ce défaut et ne pricait pas.

    Le cas des variables est pire encore : `PARAM T = 1` ne lève rien du tout,
    le paramètre est simplement illisible — toute lecture de T rend le temps
    écoulé. Une valeur plausible et fausse, jamais un message."""
    from backend.app.core.payscript.parser import RESERVED_NAMES
    # Les deux familles : fonction (échec bruyant) et variable (échec muet).
    for nom in ("FLOOR", "MIN", "T", "WOF", "INDEX"):
        assert nom in RESERVED_NAMES
        with pytest.raises(ValueError, match="mot réservé"):
            parse_script(f"PARAM {nom} = 1.0\nAT MATURITY:\n  PAY 1")
    # Sur SET aussi, au niveau 0 comme dans un corps de bloc.
    with pytest.raises(ValueError, match="mot réservé"):
        parse_script("SET WOF = 1\nAT MATURITY:\n  PAY 1")
    with pytest.raises(ValueError, match="mot réservé"):
        parse_script("AT MATURITY:\n  SET INDEX = 1\n  PAY 1")
    # Un nom voisin mais libre reste accepté.
    parse_script("PARAM PLANCHER = 1.0\nAT MATURITY:\n  PAY PLANCHER")
    parse_script("PARAM FLOOR_LVL = 1.0\nAT MATURITY:\n  PAY FLOOR_LVL")


def test_stop_commente_reste_un_rappel():
    """`STOP  # commentaire` est l'écriture idiomatique, et c'est celle que la
    référence montre. has_stop se cherchait sur le code BRUT : le commentaire
    empêchait la détection. Le produit se pricait juste et se décrivait faux —
    durée de vie espérée non calculée, rappel anticipé absent du fichier EMT,
    cycle de vie non détecté au booking."""
    base = "PARAM B = 100%\nAT 1, 2:\n  IF WOF >= B:\n    PAY 1\n    {stop}\nAT MATURITY:\n  PAY WOF"
    for forme in ("STOP", "STOP  # le contrat s'arrête ici", "STOP\t# fin", "stop # minuscules"):
        compiled = parse_script(base.format(stop=forme))
        assert compiled.has_stop, f"rappel non détecté sur : {forme!r}"
    # Et un script sans rappel ne doit pas être marqué rappelable pour autant.
    assert not parse_script("AT 1:\n  PAY 0\nAT MATURITY:\n  PAY WOF").has_stop
    # Un STOP cité dans un commentaire n'en est pas un.
    assert not parse_script("AT 1:\n  PAY 0  # pas de STOP ici\nAT MATURITY:\n  PAY WOF").has_stop


# ── Le langage documenté fonctionne réellement ──────────────────────

def test_chaque_variable_de_marche_compile():
    """Documenter un mot ne prouve pas qu'il s'utilise. On le fait tourner."""
    for nom in MARKET_VARS:
        script = f"AT 1:\n  PAY {nom} * 0\nAT MATURITY:\n  PAY 1"
        parse_script(script)          # ne doit pas lever


def test_chaque_variable_indicee_compile():
    for nom in INDEXED_VARS:
        script = f"AT 1:\n  PAY {nom}[1] * 0\nAT MATURITY:\n  PAY 1"
        parse_script(script)


def test_chaque_fonction_compile():
    unaires = {"ABS", "FLOOR", "CEIL", "SQRT", "LOG", "EXP", "INDIC", "ROUND"}
    for nom in FUNCTIONS:
        expr = f"{nom}(1)" if nom in unaires else f"{nom}(1, 2)"
        parse_script(f"AT 1:\n  PAY {expr} * 0\nAT MATURITY:\n  PAY 1")


def test_chaque_mot_logique_compile():
    for nom in LOGIC_KEYWORDS:
        cond = nom if nom in ("TRUE", "FALSE") else f"1 {nom} 1" if nom in ("AND", "OR") else f"{nom} 0"
        parse_script(f"AT 1:\n  IF {cond}:\n    PAY 0\nAT MATURITY:\n  PAY 1")


def test_les_trois_formes_de_basket_compilent():
    for expr in ("BASKET", "BASKET()", "BASKET(0.5, 0.5)"):
        parse_script(f"AT 1:\n  PAY {expr} * 0\nAT MATURITY:\n  PAY 1")


def test_l_exemple_commente_de_la_reference_parse():
    """L'exemple pédagogique du §6 doit être un vrai script. C'est celui que le
    modèle imitera le plus servilement."""
    text = REFERENCE.read_text(encoding="utf-8")
    blocs = re.findall(r"```\n(.*?)```", text, re.S)
    athena = [b for b in blocs if "Autocall Athena" in b]
    assert athena, "l'exemple commenté a disparu de la référence"
    compiled = parse_script(athena[0])
    assert compiled.has_stop
    assert len(compiled.events) == 2                       # AT 1,2,3 + AT MATURITY
    assert {p.name for p in compiled.params} == {"COUPON", "M_AC_BAR", "M_KI_BAR"}
    # La convention M_ doit être effective sur l'exemple qui la montre.
    mons = {m["name"]: m for m in compiled.monitors}
    assert mons["M_AC_BAR"]["observable"] == "WOF"
    assert mons["M_AC_BAR"]["direction"] == "up"
    assert mons["M_KI_BAR"]["direction"] == "down"


def test_tous_les_blocs_de_code_de_la_reference_sont_valides():
    """Aucun extrait de la référence ne doit être du PayScript imaginaire.
    Les extraits partiels (sans AT MATURITY) sont complétés avant parsing."""
    text = REFERENCE.read_text(encoding="utf-8")
    for bloc in re.findall(r"```\n(.*?)```", text, re.S):
        # Les extraits purement calendaires (§4) sont des lignes AT sans corps.
        if all(re.match(r"^\s*AT\s", l) or not l.strip() or l.strip().startswith("#")
               for l in bloc.splitlines()):
            continue
        src = bloc if "AT MATURITY" in bloc else bloc + "\nAT MATURITY:\n  PAY 1"
        # Un extrait référençant un CONSTAT ne se résout pas hors contexte.
        if re.search(r"^\s*AT\s+[A-Za-z_]\w*\s*(\.|:|\[)", src, re.M):
            continue
        try:
            parse_script(src)
        except ValueError as e:
            pytest.fail(f"extrait invalide dans la référence :\n{bloc}\n→ {e}")
