"""Booking input contract, independent of HTTP routing."""
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class LegalIdentityExceptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


class DealCreate(BaseModel):
    command_key: Optional[str] = Field(default=None, min_length=8, max_length=100)
    counterparty_id: Optional[int] = None
    legal_identity_exception: Optional[LegalIdentityExceptionRequest] = None
    ccr_netting_set_id: Optional[int] = None
    product_id: Optional[int] = None
    product_terms_version: Optional[int] = None
    sens: Literal["achat", "vente"] = "vente"
    contrepartie: str
    devise: str = "EUR"
    product_type: str = ""
    fixing_policy: Literal["AUTO_YAHOO"] = "AUTO_YAHOO"
    nominal: float
    fair_value: float
    price_traded: float
    trade_date: str
    strike_date: str
    value_date: str
    maturity_date: str
    payment_date: str = ""
    T: float
    underlyings: List[dict]          # [{name, ticker, s0_abs}]
    observation_times: List[float]   # unique AT times in years from value_date
    script_snapshot: str
    script_id: Optional[int] = None
    market_snapshot: dict = {}
    # Returned by /api/price. Kept nullable at schema level so a missing proof
    # reaches the audited booking refusal boundary; every accepted booking
    # requires it.
    pricing_receipt: Optional[dict] = None
    # Pre-trade opportunity this deal converts from, if any — see
    # db/models.py:Deal.indicative_id.
    indicative_id: Optional[int] = None
    # Winning RFQ response this deal was booked from, if any — see
    # db/models.py:Deal.rfq_id.
    rfq_id: Optional[int] = None
    execution_agreement_id: Optional[int] = None
    # ── Rattachement commercial (Client Intelligence) ──────────────────
    # À QUI le produit est vendu. Le reste du modèle décrit l'offre —
    # contrepartie est l'émetteur qui fait face au trade. Les trois sont
    # optionnels : un deal booké hors parcours client reste parfaitement
    # valide, simplement non rattaché.
    client_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    # L'AFFILIATION, jamais la personne : c'est ce qui empêche qu'un trade
    # change de société le jour où son interlocuteur change d'employeur.
    primary_affiliation_id: Optional[int] = None
    mandate_id: Optional[int] = None
    transaction_format: Optional[str] = None
    instrument_family: Optional[str] = None
    payoff_family: Optional[str] = None
    payoff_description: Optional[str] = None
    documentation_reference: Optional[str] = None
    commercial_reason: Optional[str] = None
