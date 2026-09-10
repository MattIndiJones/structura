"""L'échéancier résolu d'un produit, comme objet de premier ordre.

Jusqu'ici cette information n'existait nulle part. Elle se dispersait, après
`resolve_constats`, entre `CompiledEvent.dates`, `.window_dates`,
`.payment_dates`, `.ranks`, `CompiledScript.strike_fix_dates`, puis se
reconstituait différemment dans chaque consommateur — `step_map` côté Monte
Carlo, une autre boucle côté rejeu historique, une troisième côté Mark-to-Future.
C'est exactement ainsi que trois chemins finissent par décrire trois produits
légèrement différents.

Ce module en fait une **structure unique**, construite une fois à la résolution
et lisible par tous : le pricing, le backtest, le cycle de vie, l'écran Events et
le booking, qui la figera. Elle répond à la seule question qui compte pour tous :
*à cette date, que constate-t-on, sur quoi, et qu'est-ce qui s'y déclenche ?*

Trois notions, et leurs rôles ne se confondent pas :

- une **constatation** est ce que le contrat observe : elle porte un rang, une
  réduction éventuelle, une date de paiement et les blocs qui s'y exécutent ;
- un **relevé** alimente la réduction d'une constatation. Ce n'est pas une
  observation — il ne paie rien et ne compte pas dans le rang — sauf si un bloc
  le vise directement (`AT OBS[2][1]`), auquel cas il porte les deux rôles ;
- la **fenêtre de départ** fixe `S0` par sous-jacent et n'est pas une
  constatation : rien ne s'y déclenche.

Les dates sont exposées sous DEUX formes, et les deux sont nécessaires : la
year-fraction depuis le strike, sur laquelle le moteur travaille, et la date
calendaire, seule opposable — c'est elle qu'un term sheet porte, et elle qu'un
deal booké doit figer. Les reconstruire l'une depuis l'autre après coup est
précisément l'erreur d'ancrage qui est revenue cinq fois en une session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Releve:
    """Un cours qui alimente la réduction d'une constatation."""
    t: float
    jour: date | None = None
    # Un bloc `AT X[2][1]` vise ce relevé : il est alors aussi un événement, et
    # lit le COURS BRUT de ce jour-là, jamais la réduction de sa fenêtre.
    est_evenement: bool = False

    def to_dict(self) -> dict:
        return {"t": self.t, "date": self.jour.isoformat() if self.jour else None,
                "evenement": self.est_evenement}


@dataclass(frozen=True)
class Constatation:
    """Ce que le contrat observe à une date, et ce qui s'y déclenche."""
    # Nom du CONSTAT, ou None pour un bloc à dates littérales (`AT 1, 2, 3:`),
    # dont l'échéancier est sa propre liste.
    calendrier: str | None
    # Rang dans CET échéancier, base 1 — ce que le script lit sous `INDEX`.
    rang: int
    t: float
    jour: date | None = None
    # Quand le cash bouge. Distincte de l'observation : c'est elle qui porte
    # l'actualisation.
    t_paiement: float | None = None
    jour_paiement: date | None = None
    # 'MIN' | 'MAX' | 'AVG' — None pour une constatation ponctuelle.
    reduction: str | None = None
    releves: tuple[Releve, ...] = ()
    # Indices, dans `CompiledScript.events`, des blocs qui s'exécutent ici, dans
    # l'ordre du script — qui est l'ordre contractuel : un `STOP` annule les
    # suivants.
    blocs: tuple[int, ...] = ()

    @property
    def est_ponctuelle(self) -> bool:
        return self.reduction is None or not self.releves

    def to_dict(self) -> dict:
        return {
            "calendrier": self.calendrier, "rang": self.rang, "t": self.t,
            "date": self.jour.isoformat() if self.jour else None,
            "t_paiement": self.t_paiement,
            "date_paiement": (self.jour_paiement.isoformat()
                              if self.jour_paiement else None),
            "reduction": self.reduction,
            "releves": [r.to_dict() for r in self.releves],
            "blocs": list(self.blocs),
        }


@dataclass(frozen=True)
class FenetreDepart:
    """La fenêtre qui fixe `S0` par sous-jacent. Rien ne s'y déclenche."""
    reduction: str
    releves: tuple[Releve, ...]

    def to_dict(self) -> dict:
        return {"reduction": self.reduction,
                "releves": [r.to_dict() for r in self.releves]}


@dataclass(frozen=True)
class Echeancier:
    """L'échéancier contractuel résolu, dans l'ordre chronologique."""
    constatations: tuple[Constatation, ...] = ()
    depart: FenetreDepart | None = None
    # Blocs `AT MATURITY` — ils ne relèvent d'aucun échéancier, donc ne portent
    # ni rang ni date propre : ils s'exécutent à l'horizon du produit.
    blocs_maturite: tuple[int, ...] = ()

    def a_la_date(self, t: float, tol: float = 1e-9) -> tuple[Constatation, ...]:
        """Les constatations tombant à `t`. Il peut y en avoir PLUSIEURS : deux
        calendriers peuvent partager une date, et chacune garde alors son rang
        et sa réduction. C'est le cas qu'une structure indexée par la seule date
        rendrait impossible à représenter."""
        return tuple(c for c in self.constatations if abs(c.t - t) <= tol)

    @property
    def dates_de_releve(self) -> tuple[float, ...]:
        """Toutes les dates où un cours doit être relevé — constatations
        ponctuelles comprises. C'est la liste des fixings à collecter."""
        vues: dict[float, None] = {}
        for r in (self.depart.releves if self.depart else ()):
            vues[r.t] = None
        for c in self.constatations:
            for r in c.releves:
                vues[r.t] = None
            if c.est_ponctuelle:
                vues[c.t] = None
        return tuple(sorted(vues))

    def to_dict(self) -> dict:
        return {
            "depart": self.depart.to_dict() if self.depart else None,
            "constatations": [c.to_dict() for c in self.constatations],
            "blocs_maturite": list(self.blocs_maturite),
        }


def construire(script, dates_par_constat: dict | None = None,
                jours_de_releve: dict | None = None) -> Echeancier:
    """Bâtit l'échéancier depuis un `CompiledScript` déjà résolu.

    `dates_par_constat` — {nom: (jours observés, jours de paiement)} — et
    `jours_de_releve` — {nom: [[jours] par constatation]} — apportent les dates
    CALENDAIRES, que `CompiledEvent` ne transporte pas : il ne garde que des
    year-fractions. Absents, l'échéancier reste utilisable côté moteur, mais ne
    peut pas être figé au booking.
    """
    dates_par_constat = dates_par_constat or {}
    jours_de_releve = jours_de_releve or {}

    # Un relevé visé par un bloc `AT X[2][1]` : on retient sa date pour pouvoir
    # le marquer comme événement dans la fenêtre de sa constatation.
    cibles: set[tuple[str | None, float]] = set()
    for ev in script.events:
        if ev.type == "AT_MATURITY" or ev.reduction or not ev.constat_ref:
            continue
        if ev.window_dates is None and ev.ranks:
            for t in ev.dates:
                cibles.add((ev.constat_ref, round(t, 9)))

    constatations: list[Constatation] = []
    blocs_maturite: list[int] = []
    # Une constatation est identifiée par (calendrier, rang) : c'est ce qui
    # permet à deux blocs du même calendrier — `AT OBS:` et `AT OBS.last:` — de
    # se retrouver sur la MÊME constatation plutôt que d'en créer deux.
    par_cle: dict[tuple[str | None, int], list] = {}

    for idx, ev in enumerate(script.events):
        if ev.type == "AT_MATURITY":
            blocs_maturite.append(idx)
            continue
        obs, pays = dates_par_constat.get(ev.constat_ref, ([], []))
        for i, t in enumerate(ev.dates):
            rang = ev.ranks[i] if ev.ranks and i < len(ev.ranks) else i + 1
            cle = (ev.constat_ref, rang)
            # Un bloc visant un relevé partage le rang de sa constatation
            # parente sans être cette constatation : il ne doit pas en écraser
            # la réduction ni ses relevés.
            vise_un_releve = (ev.constat_ref, round(t, 9)) in cibles
            if cle in par_cle and not vise_un_releve:
                par_cle[cle].append(idx)
                continue
            if cle in par_cle:
                par_cle[cle].append(idx)
                continue
            fenetres = jours_de_releve.get(ev.constat_ref) or []
            jours = fenetres[rang - 1] if rang - 1 < len(fenetres) else []
            releves = tuple(
                Releve(t=tw, jour=jours[j] if j < len(jours) else None,
                       est_evenement=(ev.constat_ref, round(tw, 9)) in cibles)
                for j, tw in enumerate((ev.window_dates or [[]])[i]
                                       if ev.window_dates and i < len(ev.window_dates)
                                       else []))
            blocs = [idx]
            par_cle[cle] = blocs
            constatations.append(Constatation(
                calendrier=ev.constat_ref, rang=rang, t=t,
                jour=obs[rang - 1] if rang - 1 < len(obs) else None,
                t_paiement=(ev.payment_dates[i]
                            if ev.payment_dates and i < len(ev.payment_dates) else None),
                jour_paiement=pays[rang - 1] if rang - 1 < len(pays) else None,
                reduction=ev.reduction, releves=releves, blocs=blocs))

    # Les blocs ont été collectés dans des listes mutables partagées ; on les
    # fige, et on ordonne l'échéancier par date puis par calendrier.
    figees = tuple(sorted(
        (Constatation(calendrier=c.calendrier, rang=c.rang, t=c.t, jour=c.jour,
                      t_paiement=c.t_paiement, jour_paiement=c.jour_paiement,
                      reduction=c.reduction, releves=c.releves,
                      blocs=tuple(par_cle[(c.calendrier, c.rang)]))
         for c in constatations),
        key=lambda c: (c.t, c.calendrier or "", c.rang)))

    depart = None
    if script.strike_fix_reduction and script.strike_fix_dates:
        jours = jours_de_releve.get("STRIKE_FIX") or []
        plats = jours[0] if jours else []
        depart = FenetreDepart(
            reduction=script.strike_fix_reduction,
            releves=tuple(Releve(t=t, jour=plats[i] if i < len(plats) else None)
                          for i, t in enumerate(script.strike_fix_dates)))

    return Echeancier(constatations=figees, depart=depart,
                      blocs_maturite=tuple(blocs_maturite))
