from datetime import date

import pytest

from backend.app.core.calendars import (
    BusinessDayConvention,
    UnsupportedCurrency,
    add_business_days,
    adjust,
    business_days_between,
    is_business_day,
)


def test_le_calendrier_suit_la_devise_de_reglement():
    # 1er mai 2026, un vendredi : TARGET est fermé (fête du travail), les
    # États-Unis sont ouverts. Le même produit ne règle pas le même jour
    # selon la devise du cash — c'est tout l'objet du référentiel.
    premier_mai = date(2026, 5, 1)
    assert not is_business_day(premier_mai, "EUR")
    assert is_business_day(premier_mai, "USD")


def test_les_fetes_lunaires_sont_couvertes():
    # Nouvel an chinois 2026 : aucune règle de calendrier grégorien ne le
    # donne, c'est ce qui justifiait une dépendance plutôt qu'un module maison.
    assert not is_business_day(date(2026, 2, 17), "SGD")
    assert is_business_day(date(2026, 2, 17), "EUR")


def test_les_week_ends_ne_sont_jamais_ouvres():
    samedi, dimanche = date(2026, 5, 2), date(2026, 5, 3)
    for ccy in ("EUR", "USD", "GBP", "CHF", "JPY", "SGD"):
        assert not is_business_day(samedi, ccy)
        assert not is_business_day(dimanche, ccy)


def test_modified_following_ne_franchit_pas_le_mois():
    # 31 mai 2026 tombe un dimanche. Following irait au 1er juin et ferait
    # glisser une constatation de fin de trimestre sur le trimestre suivant ;
    # Modified Following recule au vendredi 29 mai.
    fin_de_mois = date(2026, 5, 31)
    assert adjust(fin_de_mois, "EUR", BusinessDayConvention.FOLLOWING) == date(2026, 6, 1)
    assert adjust(fin_de_mois, "EUR", BusinessDayConvention.MODIFIED_FOLLOWING) == date(2026, 5, 29)


def test_modified_following_avance_quand_le_mois_le_permet():
    # Samedi 2 mai 2026 : le lundi suivant reste dans le mois, on avance.
    assert adjust(date(2026, 5, 2), "EUR") == date(2026, 5, 4)


def test_un_jour_ouvre_n_est_jamais_deplace():
    ouvre = date(2026, 5, 4)
    for convention in BusinessDayConvention:
        assert adjust(ouvre, "EUR", convention) == ouvre


def test_convention_none_laisse_la_date_intacte():
    dimanche = date(2026, 5, 31)
    assert adjust(dimanche, "EUR", BusinessDayConvention.NONE) == dimanche


def test_decalage_de_reglement_saute_feries_et_week_end():
    # Jeudi 24 décembre 2026, règlement à T+2 en EUR : Noël et le 26 sont
    # fériés TARGET, le week-end suit — le cash tombe le mardi 29.
    assert add_business_days(date(2026, 12, 24), 2, "EUR") == date(2026, 12, 29)


def test_decalage_zero_ramene_sur_un_jour_ouvre():
    # T+0 un dimanche ne peut pas rester un dimanche : le cash bouge le lundi.
    assert add_business_days(date(2026, 5, 31), 0, "EUR") == date(2026, 6, 1)
    assert add_business_days(date(2026, 5, 4), 0, "EUR") == date(2026, 5, 4)


def test_decalage_negatif_remonte_le_calendrier():
    assert add_business_days(date(2026, 12, 29), -2, "EUR") == date(2026, 12, 24)


def test_comptage_et_decalage_sont_reciproques():
    depart = date(2026, 12, 24)
    arrivee = add_business_days(depart, 5, "EUR")
    assert business_days_between(depart, arrivee, "EUR") == 5
    assert business_days_between(arrivee, depart, "EUR") == -5


def test_une_devise_sans_calendrier_echoue_bruyamment():
    # Un repli silencieux sur « lundi-vendredi » décalerait le règlement d'un
    # ou deux jours sans le moindre symptôme visible.
    with pytest.raises(UnsupportedCurrency) as exc:
        is_business_day(date(2026, 5, 4), "NOK")
    assert "NOK" in str(exc.value)


def test_la_devise_est_insensible_a_la_casse():
    assert is_business_day(date(2026, 5, 4), "eur")
