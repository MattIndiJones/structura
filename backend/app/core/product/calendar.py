"""Freeze resolved calendar data, never compiled code or functions."""
from __future__ import annotations

from copy import deepcopy
from datetime import date

from ..payscript.schedule_model import Echeancier, Constatation, Releve, FenetreDepart


EVENT_FIELDS = ("dates", "payment_dates", "window_dates", "reduction", "ranks")


def freeze_calendar(compiled) -> dict:
    import hashlib
    binding = next((c for c in compiled.constats if c.role == 'initial_fixing'), None)
    return {
        "version": 2 if binding else 1,
        **({"binding": {"name": binding.underlying, "fixing": binding.name,
              "source_sha256": hashlib.sha256(binding.source.encode()).hexdigest(),
              "constats": deepcopy(binding.calendar_values), "currency": binding.calendar_currency},
            "origin": compiled.origine.isoformat()} if binding else {}),
        "events": [{"type": ev.type, **{k: deepcopy(getattr(ev, k)) for k in EVENT_FIELDS}}
                   for ev in compiled.events],
        "strike_fix_dates": compiled.strike_fix_dates,
        "strike_fix_reduction": compiled.strike_fix_reduction,
        "schedule": compiled.echeancier.to_dict(),
    }


def _day(value):
    return date.fromisoformat(value) if value else None


def _sample(row):
    return Releve(t=row["t"], jour=_day(row.get("date")), est_evenement=row.get("evenement", False))


def restore_calendar(compiled, payload: dict):
    if payload.get("version") not in (1, 2) or len(payload.get("events", [])) != len(compiled.events):
        raise ValueError("Le calendrier figé ne correspond pas au script.")
    binding = next((c for c in compiled.constats if c.role == 'initial_fixing'), None)
    if binding:
        import hashlib
        saved = payload.get('binding') or {}
        if (payload.get('version') != 2 or saved.get('name') != binding.underlying
                or saved.get('fixing') != binding.name
                or saved.get('source_sha256') != hashlib.sha256(binding.source.encode()).hexdigest()):
            raise ValueError('Le calendrier figé ne correspond pas à cette version du payoff et de son panier.')
        binding.calendar_values = deepcopy(saved['constats'])
        binding.calendar_currency = saved['currency']
        compiled.origine = _day(payload.get('origin'))
    for event, row in zip(compiled.events, payload["events"]):
        if event.type != row.get("type"):
            raise ValueError("Le type d’événement diffère du calendrier figé.")
        for key in EVENT_FIELDS:
            setattr(event, key, deepcopy(row[key]))
    compiled.strike_fix_dates = deepcopy(payload["strike_fix_dates"])
    compiled.strike_fix_reduction = payload["strike_fix_reduction"]
    schedule = payload["schedule"]
    departure = schedule.get("depart")
    compiled.echeancier = Echeancier(
        constatations=tuple(Constatation(
            calendrier=row["calendrier"], rang=row["rang"], t=row["t"], jour=_day(row.get("date")),
            t_paiement=row.get("t_paiement"), jour_paiement=_day(row.get("date_paiement")),
            reduction=row.get("reduction"), releves=tuple(_sample(x) for x in row.get("releves", [])),
            blocs=tuple(row["blocs"]),
        ) for row in schedule["constatations"]),
        depart=(FenetreDepart(reduction=departure["reduction"],
                              releves=tuple(_sample(x) for x in departure["releves"])) if departure else None),
        blocs_maturite=tuple(schedule["blocs_maturite"]),
    )
    return compiled
