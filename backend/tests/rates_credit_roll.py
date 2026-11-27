"""Independent one-pocket research roll used to qualify Structura's API responses."""

from copy import deepcopy
from datetime import date, datetime
from math import fsum, isclose, isfinite

from backend.app.core.valuation_context import canonical_fingerprint, json_transport_fingerprint


class RollReplayError(ValueError):
    """The frozen Research evidence cannot close the portfolio session."""


def number(value, label: str) -> float:
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise RollReplayError(f"Montant long invalide : {label}.")
    return float(value)


def instant(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is not None:
            return result
    except (TypeError, ValueError):
        pass
    raise RollReplayError("Une horloge avec fuseau horaire est requise.")


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise RollReplayError("Une date civile valide est requise.") from error


def _price(mark: dict) -> float:
    price = number(mark["dirty_per_100"], "dirty par 100")
    if price <= 0:
        raise RollReplayError("La cotation dirty du roll doit être strictement positive.")
    return price


class RatesCreditLedger:
    def __init__(self, instrument: str, nominal: float, reserve: float):
        self.instrument = instrument
        self.initial_quantity = number(nominal, "nominal initial") / 100
        if self.initial_quantity <= 0:
            raise RollReplayError("Le nominal initial doit être strictement positif.")
        self.cash = number(reserve, "réserve de cash")
        self.initial_nav = None
        self.vintage = None
        self.entered_on = None
        self.quantity = 0.
        self.note_pv = 0.
        self.last_settlement_day = None
        self.entered = set()
        self.claims = {}
        self.settlements = {}
        self.closed = []

    def _flow(self, flow: dict, day: date, cutoff: datetime, journals: list[dict]):
        state = flow["state"]
        scheduled = _day(flow["scheduled_date"])
        key = (self.vintage, flow["flow_id"])
        if not flow["flow_id"]:
            raise RollReplayError("Le flux doit porter une identité stable.")
        provenance = [flow.get(field) for field in ("fact_id", "version", "available_at", "validated_at", "effect_date")]
        if state == "paid" or any(value is not None for value in provenance):
            fact_id, version, available_at, validated_at, effect_date = provenance
            if (not fact_id or type(version) is not int or version < 1
                    or instant(available_at) > cutoff or instant(validated_at) > cutoff):
                raise RollReplayError(f"Flux sans preuve éligible à l’arrêté : {flow['flow_id']}.")
            effect = _day(effect_date)
        else:
            fact_id, version, available_at, validated_at = None, None, None, None
            effect = scheduled  # A due contractual principal need not originate from an external fact.
        if effect > day:
            raise RollReplayError("Le flux prend effet après l’arrêté.")
        amount = number(flow["amount_per_100"], "flux par 100")
        pv = number(flow["pv_per_100"], "PV du flux par 100")
        previous = self.claims.get(key)
        settled = self.settlements.get(key)
        proof = {"millesime_id": self.vintage, "flow_id": flow["flow_id"], "flow_kind": flow["kind"],
                 "fact_id": fact_id, "version": version, "state": state,
                 "amount_per_100": amount, "pv_per_100": pv, "effect_date": effect.isoformat(),
                 "scheduled_date": scheduled.isoformat(), "paid_date": flow.get("paid_date"),
                 "available_at": available_at, "validated_at": validated_at,
                 "quantity": self.quantity, "applied_on": day.isoformat()}
        if settled:
            cash_identity = ("state", "flow_kind", "paid_date", "scheduled_date", "amount_per_100")
            if any(proof[field] != settled[field] for field in cash_identity):
                raise RollReplayError(f"Un règlement archivé a été modifié : {flow['flow_id']}.")
            return
        if previous and not _compatible_revision(previous, proof):
            raise RollReplayError(f"Version de créance incohérente : {flow['flow_id']}.")
        if state != "paid":
            if proof["paid_date"] is not None:
                raise RollReplayError("Une créance ouverte porte une date de paiement effective.")
            self.claims[key] = proof
            if previous is None:
                journals.append({**proof, "event": "claim", "amount_eur": self.quantity * amount,
                                 "pv_eur": self.quantity * pv})
            elif previous["amount_per_100"] != amount:
                journals.append({**proof, "event": "claim_revision", "amount_eur": self.quantity * amount,
                                 "previous_amount_eur": self.quantity * previous["amount_per_100"]})
            return
        paid = _day(proof["paid_date"])
        if paid != effect or paid > day or pv != 0.:
            raise RollReplayError("Le règlement ne correspond pas à la valeur hors créance.")
        if paid < self.entered_on:
            return  # Evidence for cash paid before the index held the note.
        if previous is None:
            journals.append({**proof, "event": "claim", "amount_eur": self.quantity * amount,
                             "pv_eur": self.quantity * amount})
        self.claims.pop(key, None)
        self.settlements[key] = proof
        settled_cash = self.quantity * amount
        self.cash = fsum((self.cash, settled_cash))
        journals.append({**proof, "event": "settlement", "amount_eur": settled_cash})
        self.last_settlement_day = day

    def mark(self, mark: dict, day: date, cutoff: datetime, journals: list[dict]):
        if mark["millesime_id"] != self.vintage:
            raise RollReplayError("La marque ne correspond pas au millésime détenu.")
        state = mark["state"]
        if state == "recovery_pending":
            return False
        if state not in {"alive", "settlement_pending", "settled"}:
            raise RollReplayError("L’état de vie n’est pas pris en charge.")
        missing = set(self.claims)
        seen = set()
        for flow in sorted(mark["flows"], key=lambda row: (row["effect_date"] or "", row["flow_id"])):
            key = (self.vintage, flow["flow_id"])
            if key in seen:
                raise RollReplayError("Le reçu répète un identifiant de flux.")
            seen.add(key)
            if flow["state"] in {"due", "past_due", "paid"}:
                missing.discard(key)
                self._flow(flow, day, cutoff, journals)
        if missing:
            raise RollReplayError("Une créance déjà ouverte manque dans le reçu.")
        receivables = fsum(claim["pv_per_100"] for claim in self.claims.values())
        if not isclose(receivables, number(mark["receivable_pv_per_100"], "PV des créances"), abs_tol=1e-8, rel_tol=0):
            raise RollReplayError("Les créances détaillées ne rapprochent pas la PV reçue.")
        self.note_pv = self.quantity * number(mark["residual_pv_per_100"], "PV résiduelle")
        if state == "settled":
            if self.claims or self.note_pv != 0.:
                raise RollReplayError("Le millésime réglé porte encore une valeur ouverte.")
            self.vintage = None
            self.quantity = 0.
            self.last_settlement_day = day
        return True

    def _enter(self, quote: dict, day: date, journals: list[dict]):
        price = _price(quote)
        if quote["state"] != "alive" or quote["millesime_id"] in self.entered:
            raise RollReplayError("La cotation d’entrée doit valoriser un nouveau millésime vivant.")
        if self.initial_nav is None:
            quantity = self.initial_quantity
            cost = quantity * price
            self.initial_nav = fsum((cost, self.cash))
        else:
            cost = self.cash
            self.cash = 0.
            quantity = cost / price
        self.quantity = quantity
        self.vintage = quote["millesime_id"]
        self.entered.add(self.vintage)
        self.entered_on = day
        self.note_pv = cost
        journals.append({"event": "entry", "millesime_id": self.vintage, "price_per_100": price,
                         "quantity": quantity, "amount_eur": cost, "job_id": quote["job_id"]})

    def value(self) -> dict:
        claims = fsum(claim["quantity"] * claim["pv_per_100"] for claim in self.claims.values())
        nav = fsum((self.note_pv, claims, self.cash))
        return {"millesime_id": self.vintage, "quantity": self.quantity, "note_pv_eur": self.note_pv,
                "receivables_pv_eur": claims, "cash_eur": self.cash, "nav_eur": nav,
                "level": 100 * nav / self.initial_nav if self.initial_nav else None}

    def roll_allowed(self, day: date, *, sell_held: bool) -> bool:
        if self.initial_nav is None:
            return True
        if self.vintage:
            return self.instrument == "FRN" and sell_held and not self.claims
        return self.cash > 0. and (
            self.instrument != "CLN" or self.last_settlement_day is None or day > self.last_settlement_day
        )

    def _roll(self, quote: dict, mark: dict | None, day: date, journals: list[dict]):
        if self.vintage:
            price = _price(mark)
            cash = self.quantity * price
            if not isclose(cash, self.note_pv, abs_tol=0.000001, rel_tol=0):
                raise RollReplayError("Le prix dirty de vente et la marque résiduelle divergent.")
            self.cash = fsum((self.cash, cash))
            journals.append({"event": "sale", "millesime_id": self.vintage, "price_per_100": price,
                             "quantity": self.quantity, "amount_eur": cash, "job_id": mark["job_id"]})
        self._enter(quote, day, journals)

    def close(self, day: date, mark: dict | None, quote: dict | None, roll: dict | None, journals: list[dict]) -> dict:
        pre_roll = self.value() if self.initial_nav is not None else None
        can_roll = roll and self.roll_allowed(day, sell_held=roll.get("sell_held", False))
        if quote:
            if self.initial_nav is not None and not can_roll:
                raise RollReplayError("Le calendrier ou l’état du portefeuille interdit ce roll.")
            if roll and quote["millesime_id"] != roll["replacement_millesime_id"]:
                raise RollReplayError("La cotation d’entrée concerne un autre roll.")
            self._roll(quote, mark, day, journals)
        elif self.initial_nav is None or can_roll:
            raise RollReplayError("La cotation d’entrée requise est absente.")
        elif roll:
            journals.append({"event": "roll_deferred", "millesime_id": roll["replacement_millesime_id"],
                             "reason": "Le roll doit suivre le règlement confirmé ou la libération de la poche."})
        valuation = self.value()
        if pre_roll and quote and not isclose(pre_roll["nav_eur"], valuation["nav_eur"], abs_tol=.000001, rel_tol=0):
            raise RollReplayError("Le roll doit préserver la valeur liquidative dans le pilote sans coûts.")
        previous = self.closed[-1] if self.closed else None
        explain = _explain(previous, valuation, journals, self.initial_nav)
        row = {"day": day.isoformat(), "pre_roll": pre_roll, **valuation, "events": journals, "explain": explain,
               "receivables": sorted(self.claims.values(), key=lambda row: (row["millesime_id"], row["flow_id"])),
               "calendar_days_since_previous": (day - _day(previous["day"])).days if previous else None}
        self.closed.append(row)
        return row


def _compatible_revision(previous: dict, current: dict) -> bool:
    if current["flow_kind"] != previous["flow_kind"]:
        return False
    if current["fact_id"] != previous["fact_id"]:
        return current["state"] == "paid" and isclose(
            current["amount_per_100"] * current["quantity"], previous["amount_per_100"] * current["quantity"],
            abs_tol=.01, rel_tol=0,
        )
    if current["version"] is not None and current["version"] > previous["version"]:
        return True
    return (current["version"] == previous["version"] and current["amount_per_100"] == previous["amount_per_100"]
            and current["scheduled_date"] == previous["scheduled_date"])


def _explain(previous: dict | None, current: dict, journals: list[dict], initial_nav: float) -> dict | None:
    if not previous:
        return None
    flows = {kind: fsum(event["amount_eur"] for event in journals if event["event"] == kind)
             for kind in ("settlement", "sale", "entry")}
    recognition = fsum(event["pv_eur"] for event in journals if event["event"] == "claim")
    changes = {
        "security_marks_eur": current["note_pv_eur"] - previous["note_pv_eur"] + flows["sale"] - flows["entry"] + recognition,
        "receivable_marks_eur": current["receivables_pv_eur"] - previous["receivables_pv_eur"] + flows["settlement"] - recognition,
        "cash_carry_eur": current["cash_eur"] - previous["cash_eur"] - flows["settlement"] - flows["sale"] + flows["entry"],
        "costs_eur": 0.,
    }
    nav_move = current["nav_eur"] - previous["nav_eur"]
    return {**changes, "nav_move_eur": nav_move,
            "residual_eur": nav_move - fsum(changes.values()),
            "contributions_index_points": {key: 100 * value / initial_nav for key, value in changes.items()}}


def _validate_evidence(plan, session, job, evidence, vintages, prepared):
    job_id = job["job_id"]
    if job_id not in evidence:
        raise RollReplayError(f"Le résultat requis manque : {job_id}.")
    evidence_item = evidence[job_id]
    if not isinstance(evidence_item, dict) or set(evidence_item) != {"result", "receipt"}:
        raise RollReplayError(f"Le reçu ne correspond pas au job : {job_id}.")
    result, receipt = evidence_item["result"], evidence_item["receipt"]
    fields = ("job_id", "millesime_id", "operation")
    result_fields = ("prepared_fingerprint", "request_fingerprint", "engine_version")
    if (
        tuple(result.get(key) for key in fields) != tuple(job[key] for key in fields)
        or tuple(receipt.get(key) for key in fields) != tuple(job[key] for key in fields)
        or tuple(receipt.get(key) for key in result_fields) != tuple(result.get(key) for key in result_fields)
        or receipt.get("run_id") != plan["run_id"]
        or receipt.get("result_fingerprint") != json_transport_fingerprint(result)
        or not receipt.get("server_signature")
        or result.get("unit") != "EUR_per_100" or result.get("currency") != "EUR"
        or result.get("instrument_type") != plan["instrument_type"]
        or (result.get("valuation_date"), result.get("value_date")) != (session["day"], session["day"])
        or instant(result.get("cutoff")) != instant(session["cutoff"])
        or (result.get("market_id"), result.get("market_version")) !=
        (job["market"].get("market_id"), job["market"].get("market_version"))
    ):
        raise RollReplayError(f"Le reçu ne correspond pas au job : {job_id}.")
    millesime = job["millesime_id"]
    expected = vintages.get(millesime)
    snapshot = tuple(result.get(key) for key in ("terms_version", "terms_fingerprint", "schedule_fingerprint", "prepared_fingerprint"))
    if expected is not None and snapshot[:2] != (expected.get("terms_version", 1), canonical_fingerprint(expected["terms"])):
        raise RollReplayError(f"Les termes du millésime divergent du plan : {millesime}.")
    if prepared.setdefault(millesime, snapshot) != snapshot:
        raise RollReplayError(f"La préparation du millésime a changé : {millesime}.")
    for fact in result["events"]:
        if max(instant(fact.get("available_at")), instant(fact.get("validated_at"))) > instant(session["cutoff"]):
            raise RollReplayError(f"Le reçu utilise un fait futur : {job_id}.")
    return result


def replay_roll(plan: dict, evidence: dict[str, dict]) -> dict:
    """Reconstruct accounting from verified API envelopes, without pricing calls or IO."""
    if plan["instrument_type"] not in ("FRN", "CLN") or plan["coverage"] not in ("daily", "selected"):
        raise RollReplayError("Le plan de roll ne correspond pas à un témoin Research FRN ou CLN.")
    plan_jobs = [job["job_id"] for session in plan["sessions"] for job in session["jobs"]]
    if len(plan_jobs) != len(set(plan_jobs)) or evidence.keys() - set(plan_jobs):
        raise RollReplayError("Le dossier contient un job étranger ou dupliqué.")
    vintages = {item["millesime_id"]: item for item in plan.get("millesimes", ())}
    ledger = RatesCreditLedger(plan["instrument_type"], plan["initial_nominal_eur"], plan.get("initial_cash_reserve_eur", 0.))
    prepared, consumed = {}, {}
    source = None
    blocked = None
    state = "completed"
    previous_day = None

    def result_for(session, job):
        nonlocal source
        result = _validate_evidence(plan, session, job, evidence, vintages, prepared)
        receipt = evidence[job["job_id"]]["receipt"]
        identity = (receipt["owner_user_id"], receipt["engine_fingerprint"])
        if source is None:
            source = identity
        elif source != identity:
            raise RollReplayError("Les reçus ont des propriétaires ou des moteurs différents.")
        consumed[job["job_id"]] = deepcopy(evidence[job["job_id"]])
        return result

    for session in plan["sessions"]:
        day, cutoff = _day(session["day"]), instant(session["cutoff"])
        if day != cutoff.date() or (previous_day is not None and day <= previous_day):
            raise RollReplayError("Les dates et arrêtés doivent former une grille croissante.")
        previous_day = day
        jobs = {job["operation"]: job for job in session["jobs"]}
        if len(jobs) != len(session["jobs"]) or jobs.keys() - {"issue", "mtm"}:
            raise RollReplayError("Les jobs de la séance ne correspondent pas à une poche.")
        marking = jobs.get("mtm")
        issuing = jobs.get("issue")
        roll = session.get("roll")
        journal = []
        mark = quote = None
        if (marking["millesime_id"] if marking else None) != ledger.vintage:
            raise RollReplayError("La séance ne contient pas la marque requise de la poche détenue.")
        if marking:
            mark = result_for(session, marking)
            if not ledger.mark(mark, day, cutoff, journal):
                state = "blocked"
                blocked = {"day": session["day"], "reason": "recovery_pending",
                           "job_id": marking["job_id"], "millesime_id": ledger.vintage}
                break
        wants_entry = ledger.initial_nav is None or (roll and ledger.roll_allowed(day, sell_held=roll.get("sell_held", False)))
        if bool(issuing) != bool(wants_entry):
            raise RollReplayError("La cotation d’entrée manque ou le roll est interdit à cet arrêté.")
        if issuing:
            quote = result_for(session, issuing)
        row = ledger.close(day, mark, quote, roll, journal)
        if row["nav_eur"] == 0 and ledger.vintage is None:
            state = "extinguished"
            break
    replay = {"run_id": plan["run_id"], "coverage": plan["coverage"], "rows": ledger.closed,
              "state": state, "blocked": blocked, "plan_fingerprint": json_transport_fingerprint(plan),
              "evidence_fingerprint": json_transport_fingerprint(consumed)}
    return {**replay, "archive_fingerprint": json_transport_fingerprint(replay)}
