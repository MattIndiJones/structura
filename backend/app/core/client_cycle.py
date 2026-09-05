"""Cadence d'investissement — le moteur de cycles.

Module PUR : des dates entrent, des statistiques sortent. Ni base, ni FastAPI,
ni Yahoo. Même idiome que `core/inlife_valuation.py`, et pour la même raison —
ce qui se teste sans monter une application se teste vraiment.

Trois principes gouvernent tout ce fichier.

**La médiane plutôt que la moyenne.** Un client qui traite tous les 90 jours et
saute une année à cause d'un changement d'organisation a une moyenne fausse et
une médiane juste. La moyenne est calculée et rendue, mais elle ne décide rien.

**Une fenêtre, jamais une date.** « 15–30 octobre » est une information ;
« 22 octobre » est une illusion de précision. La largeur de la fenêtre est
dérivée de la dispersion observée — plus le passé est irrégulier, plus la
fenêtre est large. C'est le §46 de la mission, et c'est aussi la seule façon
honnête de présenter une extrapolation à partir de six observations.

**Rien plutôt que quelque chose de faux.** Sous deux trades, il n'existe aucun
intervalle : le moteur rend `insufficient_history` et s'arrête là. Fabriquer une
prédiction sur un point unique donnerait un chiffre que personne ne pourrait
contredire ni vérifier.

Aucun score composite, aucune décimale décorative. Chaque résultat porte les
observations qui l'ont produit, en français, dans `explanation` — si une phrase
ne peut pas être écrite, c'est que le chiffre n'aurait pas dû être affiché.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Optional, Sequence


# Délai de contact par défaut, quand l'historique ne permet pas de l'observer.
# Configurable parce qu'il dépend du desk : deux semaines sur un flux
# institutionnel, davantage sur une banque privée dont le comité se réunit une
# fois par mois. Lu à chaque appel, jamais figé dans une constante de module —
# un déploiement ou un test doit pouvoir le changer sans surprise d'import.
def default_lead_days() -> int:
    try:
        valeur = int(os.getenv("STRUCTURA_CLIENT_DEFAULT_LEAD_DAYS", "14"))
    except ValueError:
        return 14
    return max(1, valeur)


# Largeur minimale d'une fenêtre, en jours de part et d'autre. Une fenêtre de
# deux jours serait aussi trompeuse qu'une date : même avec une cadence
# parfaitement régulière, personne ne traite au jour près.
DEMI_LARGEUR_MINIMALE = 3

# En dessous de deux intervalles, la dispersion n'est pas mesurable. On garde
# quand même une fenêtre — mais large, et annoncée comme telle.
FRACTION_FENETRE_PAR_DEFAUT = 0.35

CONFIANCE_HAUTE = "high"
CONFIANCE_MOYENNE = "medium"
CONFIANCE_BASSE = "low"
HISTORIQUE_INSUFFISANT = "insufficient_history"


def _mediane(valeurs: Sequence[float]) -> float:
    triees = sorted(valeurs)
    n = len(triees)
    milieu = n // 2
    if n % 2:
        return float(triees[milieu])
    return (triees[milieu - 1] + triees[milieu]) / 2.0


def _quantile(valeurs: Sequence[float], q: float) -> float:
    """Quantile par interpolation linéaire, comme le fait numpy."""
    triees = sorted(valeurs)
    if len(triees) == 1:
        return float(triees[0])
    position = q * (len(triees) - 1)
    bas = int(position)
    haut = min(bas + 1, len(triees) - 1)
    return triees[bas] + (position - bas) * (triees[haut] - triees[bas])


def _demi_ecart_interquartile(valeurs: Sequence[float]) -> float:
    """Dispersion robuste : la demi-largeur de la moitié centrale des intervalles.

    L'écart-type est écarté d'emblée — une seule pause d'un an le gonflerait au
    point de rendre toute fenêtre inutile, alors qu'elle ne dit rien de la
    cadence habituelle.

    L'écart absolu médian, essayé en premier, l'est aussi : sur une série comme
    20, 200, 15, 300, 25 jours il rend 5 et conclut « mensuelle, très
    régulière ». Sa médiane des écarts tombe dans le groupe serré et ignore
    complètement les deux longues pauses. Un test l'a montré avant que le
    moteur ne serve.

    L'écart interquartile, lui, mesure l'étalement de la moitié centrale et voit
    les deux modes : sur la même série il rend 90, et la cadence est correctement
    dite irrégulière.
    """
    if len(valeurs) < 2:
        return 0.0
    return (_quantile(valeurs, 0.75) - _quantile(valeurs, 0.25)) / 2.0


def _typologie(mediane_jours: float, ratio_dispersion: float) -> str:
    """Le nom qu'on donnerait à cette cadence à l'oral.

    Une cadence trop dispersée n'a pas de nom : l'appeler « trimestrielle »
    alors qu'elle varie du simple au triple serait une étiquette fausse.
    """
    if ratio_dispersion > 0.60:
        return "irreguliere"
    if mediane_jours <= 10:
        return "hebdomadaire"
    if mediane_jours <= 45:
        return "mensuelle"
    if mediane_jours <= 135:
        return "trimestrielle"
    if mediane_jours <= 270:
        return "semestrielle"
    if mediane_jours <= 500:
        return "annuelle"
    return "pluriannuelle"


@dataclass
class Cycle:
    """Ce qu'on peut dire de la cadence d'un investisseur, et rien de plus."""
    n_trades: int
    confidence: str
    explanation: list[str] = field(default_factory=list)

    last_trade_date: Optional[str] = None
    # Journées distinctes ayant porté au moins une transaction. Un panier
    # alloué en trois lignes le même jour est UN épisode d'investissement, pas
    # trois : c'est sur ces journées que se comptent les intervalles.
    #
    # Le distinguer de `n_trades` n'est pas une coquetterie. Une première
    # version confondait les deux, et la fiche client affichait « 5
    # transactions » d'un côté et « 3 transactions observées » de l'autre, sur
    # le même écran. Les deux chiffres étaient justes ; c'est le mot qui
    # mentait, et un chiffre qu'on ne peut pas justifier vaut moins que pas de
    # chiffre du tout.
    n_trading_days: int = 0
    n_intervals: int = 0
    median_interval_days: Optional[float] = None
    mean_interval_days: Optional[float] = None
    dispersion_days: Optional[float] = None       # demi-écart interquartile
    dispersion_ratio: Optional[float] = None      # étalement central / médiane
    cadence: Optional[str] = None

    expected_window_start: Optional[str] = None
    expected_window_end: Optional[str] = None
    days_since_last: Optional[int] = None
    overdue: bool = False
    overdue_by_days: Optional[int] = None

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def has_history(self) -> bool:
        return self.confidence != HISTORIQUE_INSUFFISANT


def compute_cycle(trade_dates: Sequence[date], *,
                  asof: Optional[date] = None) -> Cycle:
    """Cadence observée à partir de dates de transaction.

    `asof` sert au calcul du retard et des fenêtres ; il se passe explicitement
    pour que les tests ne dépendent pas du jour où ils tournent.
    """
    asof = asof or date.today()
    brutes = [d for d in trade_dates if d is not None]
    # Les intervalles se comptent sur des JOURNÉES, pas sur des lignes : trois
    # allocations le même jour ne font pas trois épisodes d'investissement.
    dates = sorted(set(brutes))

    if not dates:
        return Cycle(n_trades=0, n_trading_days=0,
                     confidence=HISTORIQUE_INSUFFISANT,
                     explanation=["Aucune transaction connue."])

    dernier = dates[-1]
    ecoule = (asof - dernier).days

    if len(dates) == 1:
        return Cycle(
            n_trades=len(brutes), n_trading_days=1,
            confidence=HISTORIQUE_INSUFFISANT,
            last_trade_date=dernier.isoformat(), days_since_last=ecoule,
            explanation=[
                (f"{len(brutes)} transaction(s), toutes le même jour : aucun "
                 f"intervalle mesurable."
                 if len(brutes) > 1 else
                 "Une seule transaction connue : aucun intervalle mesurable."),
                f"Dernière transaction le {dernier.isoformat()}, il y a {ecoule} jours.",
            ])

    intervalles = [float((b - a).days) for a, b in zip(dates, dates[1:])]
    mediane = _mediane(intervalles)
    moyenne = sum(intervalles) / len(intervalles)
    dispersion = _demi_ecart_interquartile(intervalles)
    # Le ratio compare l'étalement COMPLET de la moitié centrale à la médiane :
    # c'est lui qui décide si la cadence mérite un nom.
    ratio = (2 * dispersion / mediane) if mediane > 0 else 0.0

    # Confiance : le nombre d'observations ET leur régularité. Beaucoup de
    # trades très irréguliers ne valent pas mieux que peu de trades réguliers —
    # les deux conditions doivent tenir.
    if len(intervalles) >= 5 and ratio <= 0.25:
        confiance = CONFIANCE_HAUTE
    elif len(intervalles) >= 3 and ratio <= 0.50:
        confiance = CONFIANCE_MOYENNE
    else:
        confiance = CONFIANCE_BASSE

    # Largeur de la fenêtre : la dispersion observée quand elle est mesurable,
    # une fraction large de la médiane sinon. Jamais moins de trois jours.
    # Une dispersion NULLE est une mesure, pas une absence : une cadence
    # parfaitement régulière mérite la fenêtre la plus étroite, pas la plus
    # large. Seule l'impossibilité de mesurer — un intervalle unique — justifie
    # d'élargir par défaut.
    if len(intervalles) >= 2:
        demi_largeur = max(DEMI_LARGEUR_MINIMALE, round(dispersion))
        origine_largeur = (f"moitié centrale des intervalles étalée sur "
                           f"±{round(dispersion)} jours")
    else:
        demi_largeur = max(DEMI_LARGEUR_MINIMALE,
                           round(mediane * FRACTION_FENETRE_PAR_DEFAUT))
        origine_largeur = ("dispersion non mesurable sur si peu d'observations — "
                           "fenêtre élargie par défaut")

    centre = dernier + timedelta(days=round(mediane))
    debut = centre - timedelta(days=demi_largeur)
    fin = centre + timedelta(days=demi_largeur)

    # Retard : relatif à SA propre cadence, jamais à un seuil absolu. Un client
    # trimestriel muet depuis 100 jours n'a rien d'anormal ; un client mensuel
    # muet depuis 100 jours, si.
    seuil_retard = mediane + max(dispersion, 0.25 * mediane)
    en_retard = ecoule > seuil_retard

    premiere_ligne = (
        f"{len(brutes)} transactions réparties sur {len(dates)} journées "
        f"distinctes, {len(intervalles)} intervalles."
        if len(brutes) != len(dates) else
        f"{len(dates)} transactions observées, {len(intervalles)} intervalles.")
    explication = [
        premiere_ligne,
        f"Intervalle médian de {round(mediane)} jours "
        f"(moyenne {round(moyenne)} jours).",
        f"Cadence {_typologie(mediane, ratio).replace('_', ' ')}, {origine_largeur}.",
        f"Dernière transaction le {dernier.isoformat()}, il y a {ecoule} jours.",
    ]
    if en_retard:
        explication.append(
            f"Au-delà du délai habituel : {ecoule} jours écoulés contre "
            f"{round(seuil_retard)} attendus au plus.")

    return Cycle(
        n_trades=len(brutes), n_trading_days=len(dates),
        confidence=confiance, explanation=explication,
        last_trade_date=dernier.isoformat(), n_intervals=len(intervalles),
        median_interval_days=round(mediane, 1),
        mean_interval_days=round(moyenne, 1),
        dispersion_days=round(dispersion, 1),
        dispersion_ratio=round(ratio, 3),
        cadence=_typologie(mediane, ratio),
        expected_window_start=debut.isoformat(), expected_window_end=fin.isoformat(),
        days_since_last=ecoule, overdue=en_retard,
        overdue_by_days=(ecoule - round(seuil_retard)) if en_retard else None,
    )


@dataclass
class ContactWindow:
    """Quand reprendre contact — distinct de quand la transaction est attendue."""
    start: Optional[str] = None
    end: Optional[str] = None
    lead_days: Optional[int] = None
    lead_source: str = "default"     # observed | default | none
    explanation: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def observed_lead_days(paires: Sequence[tuple[date, date]]) -> Optional[float]:
    """Délai médian entre le début des discussions et la transaction.

    `paires` = (date de première discussion, date du trade). La médiane, encore :
    un dossier qui a traîné six mois ne doit pas déplacer la recommandation
    faite sur les autres. Les paires incohérentes — discussion postérieure au
    trade — sont écartées plutôt que comptées en négatif.
    """
    delais = [float((trade - discussion).days)
              for discussion, trade in paires
              if trade >= discussion]
    if not delais:
        return None
    return _mediane(delais)


def recommend_contact_window(cycle: Cycle, *,
                             lead_days: Optional[float] = None) -> ContactWindow:
    """Recule la fenêtre d'activité attendue du délai de discussion observé.

    C'est le §49 : si le client traite entre le 20 et le 30 novembre et que les
    discussions commencent deux semaines avant, il faut l'appeler début
    novembre — pas le 20. Sans historique de cycle, il n'y a rien à reculer et
    la fenêtre n'est pas rendue : recommander une date de contact sur un client
    dont on ignore la cadence serait une recommandation inventée.
    """
    if not cycle.has_history or not cycle.expected_window_start:
        return ContactWindow(
            lead_source="none",
            explanation=["Cadence inconnue : aucune fenêtre de contact ne peut "
                         "être déduite."])

    if lead_days is None:
        delai = float(default_lead_days())
        source = "default"
        motif = (f"Délai de discussion non observable sur cet historique — "
                 f"valeur par défaut de {round(delai)} jours.")
    else:
        delai = lead_days
        source = "observed"
        motif = (f"Délai médian observé entre première discussion et transaction : "
                 f"{round(delai)} jours.")

    debut = date.fromisoformat(cycle.expected_window_start) - timedelta(days=round(delai))
    fin = date.fromisoformat(cycle.expected_window_end) - timedelta(days=round(delai))

    return ContactWindow(
        start=debut.isoformat(), end=fin.isoformat(),
        lead_days=round(delai), lead_source=source,
        explanation=[
            motif,
            f"Fenêtre d'activité attendue du {cycle.expected_window_start} au "
            f"{cycle.expected_window_end}, reculée d'autant.",
        ])


def compare_cycles(personnel: Cycle, affiliation: Cycle,
                   organisation: Cycle) -> dict:
    """Compare trois cadences sans jamais conclure à une cause.

    C'est le §42, et la limite est délibérée. On peut observer que la cadence
    d'une personne chez son nouvel employeur ressemble davantage à celle de la
    maison qu'à la sienne d'avant. On ne peut PAS en déduire que la maison la
    cause : elle a pu changer de poste, de mandat, ou de marché en même temps.
    Le module décrit, il n'explique pas.

    Rend des écarts en jours et une lecture en français, jamais un pourcentage
    d'attribution.
    """
    lecture: list[str] = []
    ecart_personnel = None
    ecart_organisation = None

    if not affiliation.has_history:
        return {"comparable": False,
                "explanation": ["Trop peu de transactions dans la société "
                                "actuelle pour comparer quoi que ce soit."]}

    courante = affiliation.median_interval_days

    if personnel.has_history and personnel.median_interval_days:
        ecart_personnel = round(abs(courante - personnel.median_interval_days), 1)
        lecture.append(
            f"Cadence actuelle {round(courante)} jours, contre "
            f"{round(personnel.median_interval_days)} jours sur l'ensemble de "
            f"son parcours (écart {ecart_personnel} jours).")

    if organisation.has_history and organisation.median_interval_days:
        ecart_organisation = round(abs(courante - organisation.median_interval_days), 1)
        lecture.append(
            f"Les autres contacts de cette société traitent tous les "
            f"{round(organisation.median_interval_days)} jours en médiane "
            f"(écart {ecart_organisation} jours).")

    ressemblance = None
    if ecart_personnel is not None and ecart_organisation is not None:
        if ecart_personnel < ecart_organisation:
            ressemblance = "personal"
            lecture.append(
                "Sa cadence actuelle reste plus proche de son propre historique "
                "que de celle de la maison — observation, pas explication.")
        elif ecart_organisation < ecart_personnel:
            ressemblance = "organization"
            lecture.append(
                "Sa cadence actuelle est plus proche de celle de la maison que "
                "de son propre historique — observation, pas explication.")
        else:
            ressemblance = "tie"
            lecture.append("Sa cadence est à égale distance des deux références.")

    return {
        "comparable": True,
        "closer_to": ressemblance,
        "gap_to_personal_days": ecart_personnel,
        "gap_to_organization_days": ecart_organisation,
        "explanation": lecture,
    }
