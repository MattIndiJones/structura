from backend.app.api.emt import _capital_tier, _detect_features
from backend.app.core.payscript.parser import parse_script


def test_un_panier_multi_actifs_n_est_pas_un_worst_of():
    script = "AT MATURITY\n  PAY BASKET\n"
    features = _detect_features(parse_script(script), 2, script)

    assert features["is_multi_asset"] is True
    assert features["has_worst_of"] is False


def test_le_worst_of_est_lu_dans_le_payoff():
    script = "AT MATURITY\n  PAY WOF\n"
    features = _detect_features(parse_script(script), 1, script)

    assert features["has_worst_of"] is True


def test_un_commentaire_ne_declenche_pas_un_worst_of():
    script = "# le mot WOF est seulement documentaire\nAT MATURITY\n  PAY BASKET\n"
    features = _detect_features(parse_script(script), 2, script)

    assert features["has_worst_of"] is False


def test_un_libelle_de_flux_ne_declenche_pas_un_worst_of():
    script = 'AT MATURITY\n  PAY BASKET "panier, pas un WOF"\n'
    features = _detect_features(parse_script(script), 2, script)

    assert features["has_worst_of"] is False


def test_seule_une_protection_contractuelle_complete_et_inconditionnelle_est_garantie():
    garantie = _capital_tier(100.0, "unconditional")

    assert garantie["tier"] == "garanti"
    assert garantie["level_pct"] == 100.0
    assert garantie["condition"] == "unconditional"
    assert garantie["source"] == "contract"
    assert _capital_tier(100.0, "conditional")["tier"] == "indetermine"
    assert _capital_tier(98.0, "unconditional")["tier"] == "indetermine"
    assert _capital_tier(None, "unknown")["tier"] == "indetermine"


def test_le_levier_emt_lit_la_valeur_economique_saisie():
    script = "PARAM GEARING = 50%\nAT MATURITY\n  PAY GEARING * WOF\n"
    compiled = parse_script(script)
    assert _detect_features(compiled, 1, script)["has_leverage"] is False
    assert _detect_features(
        compiled, 1, script, {"GEARING": 2.0})["has_leverage"] is True
