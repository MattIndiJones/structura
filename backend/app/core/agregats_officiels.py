"""L'agrégat officiel d'une constatation moyennée — point 6 du §14.

Une constatation sur période n'est pas observable : elle se calcule depuis les
cours de sa fenêtre. Ce module fait ce calcul, et surtout il dit quand il ne
peut PAS le faire.

Deux principes, et le second compte autant que le premier :

**La réduction est par sous-jacent.** `AVG` moyenne chaque actif sur ses propres
relevés ; `MIN` et `MAX` prennent son extrême à lui. L'agrégation panier —
worst-of, best-of, moyenne — vient après, dans le payoff, jamais ici. Réduire
l'agrégat au lieu de chaque actif donne un autre produit :
`moyenne(min) <= min(moyennes)` toujours, et l'écart se chiffre en dizaines de
points de base sur un worst-of.

**Une fenêtre incomplète ne rend pas d'agrégat.** Pas de moyenne sur les relevés
disponibles, pas d'extrapolation : le calcul est refusé et dit ce qui manque.
Une moyenne partielle qui se présenterait comme une moyenne est exactement le
genre de chiffre faux qui ne se signale pas. C'est l'invariant « aucune moyenne
partielle silencieuse » du plan.

Mais un blocage sans issue en est un aussi : un férié imprévu, une source
indisponible, un titre suspendu bloqueraient un produit que personne ne pourrait
débloquer. D'où la **neutralisation tracée** — un relevé peut être écarté, à
condition que la raison et son auteur voyagent avec le calcul.
"""
from __future__ import annotations

from dataclasses import dataclass, field


REDUCTIONS = ("MIN", "MAX", "AVG")


@dataclass(frozen=True)
class Neutralisation:
    """Un relevé délibérément écarté du calcul, et pourquoi.

    Jamais un défaut silencieux : sans motif ni auteur, un relevé manquant
    bloque. C'est le seul moyen d'aller au bout d'une fenêtre qu'un événement
    de marché a rendue incomplète, et il laisse une trace."""
    date: str
    motif: str
    par: str

    def to_dict(self) -> dict:
        return {"date": self.date, "motif": self.motif, "par": self.par}


@dataclass(frozen=True)
class Agregat:
    """Le niveau constaté d'une observation moyennée, ou la raison de son
    absence."""
    calculable: bool
    reduction: str = ""
    # {nom du sous-jacent: niveau réduit}. Vide quand non calculable.
    niveaux: dict = field(default_factory=dict)
    # Dates de relevé attendues et non fournies — ce qui bloque, nommément.
    manquants: tuple[str, ...] = ()
    # Sous-jacents absents d'au moins un relevé fourni : un actif ne peut pas
    # être réduit sur une fenêtre où il n'a pas tous ses cours.
    incomplets: tuple[str, ...] = ()
    neutralises: tuple[Neutralisation, ...] = ()
    # Versions de fixing ayant servi : c'est ce qui permet de dire qu'un agrégat
    # est périmé quand l'une d'elles est corrigée.
    versions: tuple[int, ...] = ()
    motif: str = ""

    def to_dict(self) -> dict:
        return {
            "calculable": self.calculable, "reduction": self.reduction,
            "niveaux": dict(self.niveaux), "manquants": list(self.manquants),
            "incomplets": list(self.incomplets),
            "neutralises": [n.to_dict() for n in self.neutralises],
            "versions": list(self.versions), "motif": self.motif,
        }


def _reduire(valeurs: list[float], reduction: str) -> float:
    if reduction == "MIN":
        return min(valeurs)
    if reduction == "MAX":
        return max(valeurs)
    return sum(valeurs) / len(valeurs)


def calculer(reduction: str, attendus: list[str], fournis: dict,
             neutralises: tuple[Neutralisation, ...] = ()) -> Agregat:
    """Réduit une fenêtre en un niveau par sous-jacent.

    `attendus` — les dates de relevé que l'échéancier figé exige.
    `fournis` — {date: {"spots": {actif: cours}, "version": n}}, les fixings
    officiels validés, tels que le cycle de vie les a enregistrés.
    `neutralises` — les relevés délibérément écartés, avec motif et auteur.

    Rend un `Agregat` non calculable plutôt que de lever : l'appelant doit
    pouvoir afficher ce qui manque, pas gérer une exception.
    """
    if reduction not in REDUCTIONS:
        return Agregat(False, motif=f"réduction inconnue : {reduction!r}")

    ecartes = {n.date for n in neutralises}
    requis = [d for d in attendus if d not in ecartes]
    if not requis:
        return Agregat(False, reduction=reduction, neutralises=tuple(neutralises),
                       motif="tous les relevés de la fenêtre ont été neutralisés — "
                             "il ne reste rien à réduire")

    manquants = tuple(d for d in requis if d not in fournis)
    if manquants:
        return Agregat(
            False, reduction=reduction, manquants=manquants,
            neutralises=tuple(neutralises),
            motif=f"fenêtre incomplète : {len(manquants)} relevé(s) sur "
                  f"{len(requis)} sans fixing officiel. Une moyenne partielle "
                  f"n'est pas une moyenne — fournissez les fixings manquants, ou "
                  f"neutralisez-les avec un motif.")

    # Un actif ne peut être réduit que s'il a TOUS ses cours sur la fenêtre :
    # le réduire sur ce qui existe le comparerait à ses pairs sur une base
    # différente, dans le calcul même du worst-of.
    par_actif: dict[str, list[float]] = {}
    for d in requis:
        for nom, cours in (fournis[d].get("spots") or {}).items():
            par_actif.setdefault(nom, []).append(float(cours))
    incomplets = tuple(sorted(nom for nom, v in par_actif.items() if len(v) != len(requis)))
    if incomplets or not par_actif:
        return Agregat(
            False, reduction=reduction, incomplets=incomplets,
            neutralises=tuple(neutralises),
            motif=(f"sous-jacent(s) sans cours sur toute la fenêtre : "
                   f"{', '.join(incomplets)}" if incomplets else
                   "aucun cours fourni sur la fenêtre"))

    versions = tuple(sorted({int(fournis[d].get("version") or 0) for d in requis}))
    return Agregat(
        True, reduction=reduction,
        niveaux={nom: _reduire(v, reduction) for nom, v in sorted(par_actif.items())},
        neutralises=tuple(neutralises), versions=versions)


def est_perime(agregat: Agregat, versions_courantes: dict, attendus: list[str],
               fournis: dict) -> bool:
    """Un agrégat calculé sur des fixings depuis corrigés est périmé.

    Une correction crée une nouvelle version : tout ce qui a été décidé sur
    l'ancienne — proposition de cycle de vie, niveau constaté publié — doit
    cesser d'être applicable. Comparer les versions plutôt que les valeurs :
    une correction qui rend le même cours reste une correction, et l'auditeur
    doit voir qu'elle a eu lieu.
    """
    if not agregat.calculable:
        return False
    ecartes = {n.date for n in agregat.neutralises}
    actuelles = {int(versions_courantes.get(d, (fournis.get(d) or {}).get("version") or 0))
                 for d in attendus if d not in ecartes}
    return actuelles != set(agregat.versions)
