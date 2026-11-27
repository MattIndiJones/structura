"""Economic results shared by the booked exotic lifecycle pricers."""
from dataclasses import dataclass
from datetime import date
from typing import Literal

from ..core.product.models import FrozenModel


class ResidualFlow(FrozenModel):
    flow_id: str
    payment_event_id: str
    payment_date: date
    state: Literal["projected", "receivable", "due", "overdue", "paid"]
    amount_eur: float
    pv_eur: float
    fixing_fact_ids: tuple[int, ...] = ()
    payment_fact_id: int | None = None


@dataclass(frozen=True)
class ExoticResidual:
    state: Literal["alive", "recovery_pending", "settlement_pending", "settled"]
    dirty_pv_eur: float | None
    residual_pv_eur: float | None
    receivables_pv_eur: float
    ci95_eur: tuple[float, float] | None
    flows: tuple[ResidualFlow, ...]
