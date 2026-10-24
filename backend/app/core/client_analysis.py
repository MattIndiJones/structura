"""Explicit currency units and temporal basis for CRM observations."""
from collections import defaultdict
from datetime import date
import math
from statistics import median


def currency_code(value):
    code=str(value or '').strip().upper()
    return code if len(code)==3 and code.isascii() and code.isalpha() else None


def amount_summary(values):
    buckets=defaultdict(list)
    unqualified=0
    for currency,amount in values:
        code=currency_code(currency)
        if code is None or isinstance(amount,bool) or not isinstance(amount,(int,float)) or not math.isfinite(amount):
            unqualified+=1
            continue
        buckets[code].append(float(amount))
    groups={code:{'amount':math.fsum(sorted(items)),'median':median(items),'count':len(items)}
            for code,items in sorted(buckets.items())}
    single=next(iter(groups)) if len(groups)==1 and not unqualified else None
    return {'by_currency':groups,'currency':single,'unqualified_count':unqualified,
            'amount':groups[single]['amount'] if single else (0.0 if not groups and not unqualified else None),
            'median':groups[single]['median'] if single else None}


def temporal_basis(asof):
    return {'transactions':'TRADE_DATE_ON_OR_BEFORE_ASOF','transaction_asof':asof.isoformat(),
            'opportunities':'CURRENT_STATE','reference_asof':date.today().isoformat(),
            'historical_opportunity_state_reconstructed':False,
            'knowledge_time_reconstructed':False}
