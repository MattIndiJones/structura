"""Explicit cash income supplied with an investor's study (never inferred from NAV)."""
import csv
import datetime as dt
import math


def load_cash_income(path, currency, start, end):
    if not path:
        return None
    income = 0.0
    seen = set()
    with open(path, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            day = dt.date.fromisoformat(row["date"])
            kind = row["type"]
            if kind not in {"INITIAL_CAPITAL", "DIVIDEND", "MANAGEMENT_FEE_PAYMENT", "PERFORMANCE_FEE_PAYMENT"}:
                raise ValueError(f"Type de flux non pris en charge : {kind}")
            amount = float(row["amount_local"])
            # Generic product-currency column; legacy USD fixture is accepted only for USD funds.
            value = float(row["amount_prod"] if "amount_prod" in row else row["amount_usd"] if currency == "USD" else "nan")
            if not math.isfinite(value) or not math.isfinite(amount):
                raise ValueError("Montant de flux absent ou non fini dans la devise du fonds")
            if row.get("currency") == currency and not math.isclose(value, amount, rel_tol=1e-12, abs_tol=1e-8):
                raise ValueError("Flux dans la devise du fonds : montants local et converti incohérents")
            if currency == "USD" and row.get("usd_per_local"):
                rate = float(row["usd_per_local"])
                if not math.isfinite(rate) or rate <= 0 or not math.isclose(amount * rate, value, rel_tol=1e-12, abs_tol=1e-8):
                    raise ValueError("Conversion FX du flux incohérente")
            key = (row["date"], kind, row.get("asset_id", ""))
            if key in seen:
                raise ValueError("Flux dupliqué : agréger les paiements par date, type et titre")
            seen.add(key)
            if start <= day.isoformat() <= end and kind == "DIVIDEND":
                income += value
    return income
