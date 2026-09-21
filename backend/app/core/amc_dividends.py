"""Dated dividend receivables and auditable reinvestment; no market side effects."""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DividendPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    status: Literal["unknown", "none", "provided"] = "unknown"
    treatment: Literal["cash", "automatic", "discretionary"] = "cash"
    destination: Literal["same_asset", "basket"] = "same_asset"
    allocations: dict[str, float] = Field(default_factory=dict)
    execution_source: Literal["orders", "reconstruct"] = "orders"
    delay_weekdays: int = Field(default=0, ge=0, le=365)
    fractional_shares: bool = True
    reinvestment_fee_pct: float | None = Field(default=None, ge=0, lt=100)
    documentation: str = ""

    @model_validator(mode="after")
    def validate_policy(self):
        if self.destination == "basket" and (not self.allocations or
                any(not k.strip() or not math.isfinite(v) or v <= 0 for k, v in self.allocations.items()) or
                not math.isclose(sum(self.allocations.values()), 1, abs_tol=1e-9)):
            raise ValueError("Les allocations de réinvestissement doivent être positives et totaliser 1")
        if self.execution_source == "reconstruct" and self.treatment != "automatic":
            raise ValueError("Reconstruction réservée au réinvestissement automatique documenté")
        return self


class Execution(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    asset_id: str = Field(min_length=1)
    date: dt.date
    order_id: str | None = None
    price_local: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    fx_to_fund: float | None = Field(default=None, gt=0)


class DividendEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    ex_date: dt.date
    payment_date: dt.date
    eligible_quantity: float | None = Field(default=None, ge=0)
    # Converts quantities in the order-book basis into ex-date share units.
    entitlement_unit_factor: float = Field(default=1, gt=0)
    gross_per_share: float | None = Field(default=None, ge=0)
    gross_local: float | None = Field(default=None, ge=0)
    net_local: float | None = Field(default=None, ge=0)
    withholding_local: float | None = Field(default=None, ge=0)
    withholding_rate: float | None = Field(default=None, ge=0, le=1)
    fx_at_ex: float | None = Field(default=None, gt=0)
    fx_at_payment: float | None = Field(default=None, gt=0)
    fx_at_valuation: float | None = Field(default=None, gt=0)
    fx_valuation_date: dt.date | None = None
    executions: list[Execution] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_event(self):
        if self.payment_date < self.ex_date:
            raise ValueError("Paiement antérieur au détachement")
        if self.gross_local is None and self.gross_per_share is None and self.net_local is None:
            raise ValueError("Montant brut, net ou par action requis")
        if self.withholding_local is not None and self.withholding_rate is not None:
            raise ValueError("Fournir soit une retenue en montant, soit un taux")
        return self


def _day(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(value)


def _execution_day(payment, delay):
    day = payment
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    for _ in range(delay):
        day += dt.timedelta(days=1)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
    return day


def _rate(ccy, fund, value):
    if ccy == fund:
        if value is not None and value != 1:
            raise ValueError("Change intra-devise différent de 1")
        return 1.0
    if value is None:
        raise ValueError("Change du dividende manquant (devise du fonds par unité locale)")
    return value


def _summary(status, rows, generated=None, adjustments=0, issues=None):
    fields = ["net_income_prod", "income_at_ex_prod", "fx_pnl_prod", "paid_prod", "receivable_prod", "reinvested_prod", "reinvestment_cost_prod"]
    by_asset = {}
    for row in rows:
        slot = by_asset.setdefault(row["asset_id"], {field: 0.0 for field in fields})
        for field in fields:
            slot[field] += row.get(field, 0.0)
    totals = {field: sum(row.get(field, 0.0) for row in rows) for field in fields}
    return {"status": status, "events": rows, "by_asset": by_asset,
            "totals": totals if status != "unknown" else {f: None for f in fields},
            "generated_orders": generated or [], "transaction_fee_adjustment": adjustments,
            "issues": issues or []}


def legacy_dividends(path, currency, start, end):
    """Existing payment ledger remains supported, but cannot prove ex-date accounting."""
    from .amc_cash_events import load_cash_income
    load_cash_income(path, currency, start, end)  # shared format/duplicate/FX controls
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as stream:
        for r in csv.DictReader(stream):
            if r["type"] != "DIVIDEND" or not start <= r["date"] <= end:
                continue
            value = float(r["amount_prod"] if "amount_prod" in r else r["amount_usd"])
            rows.append({"id": f'payment:{r["date"]}:{r.get("asset_id", "")}',
                         "asset_id": r.get("asset_id", ""), "ex_date": None, "payment_date": r["date"],
                         "gross_local": None, "withholding_local": None, "net_local": float(r["amount_local"]),
                         "currency": r["currency"], "net_income_prod": value, "income_at_ex_prod": value,
                         "fx_pnl_prod": 0, "paid_prod": value, "receivable_prod": 0,
                         "reinvested_prod": 0, "reinvestment_cost_prod": 0, "source": "payment_ledger"})
    return _summary("payments_only", rows, issues=["Relevé de paiements seul : dates de détachement, créances et fiscalité non documentées"])


def prepare_dividends(path, legacy_path, policy, orders, start, end, fund_currency,
                      initial_positions=None, units=1, transaction_fee_pct=0):
    """Events must use the same share basis as the normalized order book.

    Reconstructed purchases use explicitly dated supplied execution prices; no invented quotes.
    The original order book is never mutated or written back.
    """
    policy = DividendPolicy.model_validate(policy)
    if path and legacy_path:
        # Legacy payment totals are not added again when the dated ledger is authoritative.
        from .amc_cash_events import load_cash_income
        load_cash_income(legacy_path, fund_currency, start, end)
    if not path:
        if policy.status == "provided":
            raise ValueError("Le statut dividendes renseignés exige un fichier d'événements datés")
        legacy = legacy_dividends(legacy_path, fund_currency, start, end) if legacy_path else None
        if policy.status == "none":
            if legacy and legacy["events"]:
                raise ValueError("Absence de dividendes contredite par les flux fournis")
            return _summary("none", [])
        return legacy or _summary("unknown", [])
    if policy.status != "provided":
        raise ValueError("Un fichier dividendes exige le statut renseignés")
    with open(path, encoding="utf-8-sig") as stream:
        raw = json.load(stream)
    if not isinstance(raw, dict) or not isinstance(raw.get("events"), list) or len(raw["events"]) > 20000:
        raise ValueError("Format dividendes attendu : objet events, maximum 20 000 événements")
    events = [DividendEvent.model_validate(e) for e in raw["events"]]
    ids = [e.id for e in events]
    keys = [(e.asset_id, e.ex_date, e.payment_date) for e in events]
    if len(set(ids)) != len(ids) or len(set(keys)) != len(keys):
        raise ValueError("Dividende dupliqué : agréger les montants par titre et dates")
    if any(e.ex_date < _day(start) <= e.payment_date for e in events):
        raise ValueError("Créance antérieure au début de période : bilan d'ouverture requis")
    work = list(orders)
    order_map = {o["id"]: o for o in orders}
    seed = {p["isin"]: units*p["qty_per_cert"] for p in initial_positions or []}
    rows, generated, issues, used_orders = [], [], [], set()
    adjustment = 0.0
    for event in sorted(events, key=lambda e: (e.ex_date, e.id)):
        if not _day(start) <= event.ex_date <= _day(end):
            continue
        qty = (seed.get(event.asset_id, 0) + sum(o["executed_qty"] for o in work
               if o["isin"] == event.asset_id and o["state"] == "Done" and _day(o["date"]) < event.ex_date)) * event.entitlement_unit_factor
        if qty < -1e-8:
            raise ValueError("Dividendes courts non pris en charge par ce registre long only")
        qty = max(qty, 0)
        if event.eligible_quantity is not None and not math.isclose(qty, event.eligible_quantity, rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError(f"Quantité donnant droit au dividende non rapprochée : {event.id}")
        gross = event.gross_local
        if event.gross_per_share is not None:
            calculated = qty*event.gross_per_share
            if gross is not None and not math.isclose(calculated, gross, rel_tol=1e-8, abs_tol=.00001):
                raise ValueError(f"Montant par action incohérent : {event.id}")
            gross = calculated
        if qty == 0 and ((gross or 0) > 0 or (event.net_local or 0) > 0):
            raise ValueError(f"Dividende sans position éligible : {event.id}")
        tax = event.withholding_local
        if event.withholding_rate is not None:
            if gross is None:
                raise ValueError("Montant brut requis pour appliquer une retenue proportionnelle")
            tax = gross*event.withholding_rate
        net = event.net_local
        if gross is not None and net is not None:
            if tax is None:
                tax = gross-net
            elif not math.isclose(gross-tax, net, abs_tol=.00001, rel_tol=1e-9):
                raise ValueError("Brut, net et retenue incohérents")
        if net is None:
            if tax is None:
                raise ValueError("Retenue inconnue : préciser zéro ou le montant net")
            net = gross-tax
        if net < 0 or (tax is not None and tax < 0):
            raise ValueError("Dividende net ou retenue négatifs")
        ex_rate = _rate(event.currency, fund_currency, event.fx_at_ex)
        paid = event.payment_date <= _day(end)
        if paid:
            rate = _rate(event.currency, fund_currency, event.fx_at_payment)
        else:
            if event.currency != fund_currency and event.fx_valuation_date != _day(end):
                raise ValueError("Change de la créance requis à la date exacte de l'arrêté")
            rate = _rate(event.currency, fund_currency, event.fx_at_valuation)
        value = net*rate
        row = {"id": event.id, "asset_id": event.asset_id, "ex_date": str(event.ex_date),
               "payment_date": str(event.payment_date), "eligible_quantity": qty, "currency": event.currency,
               "gross_local": gross, "withholding_local": tax, "net_local": net,
               "income_at_ex_prod": net*ex_rate, "fx_pnl_prod": net*(rate-ex_rate), "net_income_prod": value,
               "paid_prod": value if paid else 0, "receivable_prod": 0 if paid else value,
               "reinvested_prod": 0.0, "reinvestment_cost_prod": 0.0, "source": "dated_events", "order_ids": []}
        if policy.treatment != "automatic" and event.executions:
            raise ValueError("Liens de réinvestissement fournis sans convention automatique")
        if policy.treatment == "automatic":
            execution_day = _execution_day(event.payment_date, policy.delay_weekdays)
            if execution_day <= _day(end) and net > 0:
                if not event.executions:
                    issues.append(f"Réinvestissement non documenté : {event.id}")
                else:
                    allocations = {event.asset_id: 1.0} if policy.destination == "same_asset" else policy.allocations
                    if {x.asset_id for x in event.executions} != set(allocations) or len(event.executions) != len(allocations):
                        raise ValueError("Une exécution par destination de réinvestissement est requise")
                    for x in event.executions:
                        if x.date != execution_day:
                            raise ValueError("Date d'exécution incompatible avec la règle de réinvestissement")
                        fee_pct = policy.reinvestment_fee_pct if policy.reinvestment_fee_pct is not None else (transaction_fee_pct or 0)
                        budget = value*allocations[x.asset_id]
                        if policy.execution_source == "orders":
                            o = order_map.get(x.order_id)
                            if not o or o["state"] != "Done" or o["executed_qty"] <= 0 or o["isin"] != x.asset_id or _day(o["date"]) != x.date:
                                raise ValueError("Achat de réinvestissement absent ou incompatible dans le carnet")
                            if x.order_id in used_orders:
                                raise ValueError("Un achat ne peut être affecté à plusieurs dividendes")
                            used_orders.add(x.order_id)
                            notional = o["executed_qty"]*o["price_prod"]
                        else:
                            if x.order_id or any(o["isin"] == x.asset_id and o["state"] == "Done" and o["executed_qty"] > 0 and _day(o["date"]) == x.date for o in orders):
                                raise ValueError("Achat déjà présent ou ambigu : utiliser le lien au carnet")
                            if x.price_local is None or x.currency is None:
                                raise ValueError("Prix et devise d'exécution requis pour reconstruire un achat")
                            execution_fx = _rate(x.currency, fund_currency, x.fx_to_fund)
                            quantity = budget/(1+fee_pct/100)/(x.price_local*execution_fx)
                            if not policy.fractional_shares:
                                quantity = math.floor(quantity)
                            notional = quantity*x.price_local*execution_fx
                            oid = f"DIV_REINVEST:{event.id}:{x.asset_id}"
                            if oid in order_map:
                                raise ValueError("Identifiant de réinvestissement déjà présent")
                            o = {"id": oid, "date": dt.datetime.combine(x.date, dt.time()), "state": "Done", "isin": x.asset_id,
                                 "name": x.asset_id, "ccy": x.currency, "executed_qty": quantity, "ordered_qty": quantity,
                                 "price_local": x.price_local, "fx": execution_fx, "price_prod": x.price_local*execution_fx,
                                 "notional_prod": notional, "side": "BUY", "dividend_reconstructed": True}
                            if quantity > 0:
                                generated.append(o)
                                work.append(o)
                        cost = notional*fee_pct/100
                        if notional+cost > budget + .00001:
                            raise ValueError("Réinvestissement supérieur au dividende net disponible")
                        if policy.execution_source == "orders" and not policy.fractional_shares and not math.isclose(o["executed_qty"], round(o["executed_qty"]), abs_tol=1e-8):
                            raise ValueError("Actions fractionnaires interdites par la convention")
                        row["reinvested_prod"] += notional
                        row["reinvestment_cost_prod"] += cost
                        if notional > 0:
                            row["order_ids"].append(o["id"])
                        adjustment += cost-notional*(transaction_fee_pct or 0)/100
        row["cash_after_reinvestment_prod"] = row["paid_prod"]-row["reinvested_prod"]-row["reinvestment_cost_prod"]
        rows.append(row)
    if legacy_path:
        legacy = legacy_dividends(legacy_path, fund_currency, start, end)
        paid = defaultdict(float)
        for row in rows:
            paid[row["asset_id"]] += row["paid_prod"]
        for asset in set(paid) | set(legacy["by_asset"]):
            if not math.isclose(paid[asset], legacy["by_asset"].get(asset, {}).get("paid_prod", 0), rel_tol=1e-9, abs_tol=.00001):
                raise ValueError(f"Paiements de dividendes contradictoires entre les deux registres : {asset}")
    return _summary("provided", rows, generated, adjustment, issues)
