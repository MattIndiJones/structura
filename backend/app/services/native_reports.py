"""Indicative KID and EMT material from native deterministic pricing evidence."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from ..core.product.credit_results import CreditContext, CreditResult
from ..core.product.models import FrozenModel
from ..core.product.native_market import NativeValuationContext
from ..core.product.rates_pricing import RatesPriceResult
from .exotic_reports import TargetMarketDecision
from .native_valuation_explain import Family, _product
from .product_repository import ProductError


PROFILE = "native-deterministic-report-v1"
_RATES_RESULT = TypeAdapter(RatesPriceResult)


class _ReportSource(FrozenModel):
    family: Family
    receipt: dict | None = Field(default=None, min_length=1)
    product_id: int | None = Field(default=None, strict=True, gt=0)
    calculation_id: int | None = Field(default=None, strict=True, gt=0)

    @model_validator(mode="after")
    def exactly_one_source(self):
        source = (self.receipt is not None, self.product_id is not None, self.calculation_id is not None)
        if source not in ((True, False, False), (False, True, True)):
            raise ValueError("Fournissez un reçu signé ou la référence d’un calcul Product conservé.")
        return self


class NativeKidCall(_ReportSource):
    report: Literal["kid"]
    upfront_eur: float | None = Field(default=None, gt=0)
    entry_cost_eur: float | None = Field(default=None, ge=0)


class NativeEmtCall(_ReportSource):
    report: Literal["emt"]
    decision: TargetMarketDecision


NativeReportCall = Annotated[NativeKidCall | NativeEmtCall, Field(discriminator="report")]


class NativeReportMeasure(FrozenModel):
    kind: Literal["frn_clean_price", "irs_net_pv", "cds_clean_price", "cln_clean_price", "credit_pv"]
    unit: Literal["EUR", "per_100_notional"]
    value: float | None


class _NativeReport(FrozenModel):
    schema_version: Literal[1] = 1
    instrument_type: Literal["FRN", "IRS", "CDS", "CLN"]
    family: Family
    product_id: int | None
    product_reference: str | None
    terms_version: int | None
    terms_fingerprint: str
    schedule_fingerprint: str
    context_fingerprint: str
    valuation_date: date
    cutoff: AwareDatetime
    maturity_date: date | None
    effective_date: date | None
    currency: Literal["EUR"] = "EUR"
    nominal_eur: float
    side: Literal["BUY", "SELL"]
    measure: NativeReportMeasure
    economic_pv_eur: float | None
    market_quality: Literal["synthetic", "published_historical_benchmark"]
    position_state: Literal["alive", "recovery_pending", "settlement_pending", "settled"] | None
    payoff_mode: Literal["native", "scripted"]
    features: tuple[str, ...]


class NativeKidPreview(_NativeReport):
    report: Literal["kid"] = "kid"
    method: Literal["deterministic_contract_summary"] = "deterministic_contract_summary"
    status: Literal["INDICATIVE_NON_PRIIPS"] = "INDICATIVE_NON_PRIIPS"
    scenarios_available: Literal[False] = False
    upfront_eur: float | None
    entry_cost_eur: float | None
    required_for_qualification: tuple[str, ...] = (
        "Déterminer l’applicabilité et la catégorie du produit, puis valider la période de détention.",
        "Qualifier les historiques ou proxys des facteurs de risque et les scénarios de performance et de tension.",
        "Justifier le risque de crédit pertinent, les coûts totaux et la méthode de restitution.",
        "Soumettre le document et les chiffres à une validation indépendante.",
    )


class NativeEmtPreview(_NativeReport):
    report: Literal["emt"] = "emt"
    method: Literal["desk_target_market_review"] = "desk_target_market_review"
    status: Literal["INDICATIVE_NON_FINDATEX"] = "INDICATIVE_NON_FINDATEX"
    decision: TargetMarketDecision
    matters_to_review: tuple[str, ...]
    required_for_qualification: tuple[str, ...] = (
        "Valider le marché cible, le marché cible négatif et les canaux avec le responsable produit.",
        "Qualifier les données de coûts, les champs applicables et le format d’échange retenu.",
    )


NativeReport = NativeKidPreview | NativeEmtPreview


_FEATURES = {
    "FRN": ("Coupon variable lié à l’indice Euribor contractuel et à sa marge.",
            "Remboursement du principal soumis au risque de crédit de l’émetteur de la note."),
    "IRS": ("Échange de flux d’intérêt fixes et variables dans le sens contractuel, sans échange du nominal.",
            "Exposition à la projection, à l’actualisation et au risque de contrepartie."),
    "CDS": ("Prime de crédit et protection sur le défaut de l’entité de référence.",
            "La perspective acheteur ou vendeur détermine le sens des flux de protection."),
    "CLN": ("Coupon fixe conditionné à la survie de la référence et remboursement au recouvrement en cas de défaut.",
            "Le risque de crédit de l’émetteur de la note est distinct du risque de l’entité de référence."),
}


def _terms_report(claims: dict, family: Family) -> dict:
    try:
        if family == "rates":
            context = NativeValuationContext.model_validate(claims["context"])
            result = _RATES_RESULT.validate_python(claims["result"])
            product = _product(claims, context)
            result_binding = (result.product_id, result.terms_version, result.terms_fingerprint, result.schedule_fingerprint,
                              result.context_fingerprint, result.value_date)
            expected = (context.product_id, context.terms_version, context.terms_fingerprint, context.schedule_fingerprint,
                        context.fingerprint, context.value_date)
            if result_binding != expected:
                raise ValueError("Le résultat de taux ne correspond pas au contexte signé.")
            economic_pv, side, state = result.economic_pv_eur, result.position_side, None
        else:
            context = CreditContext.model_validate(claims["context"])
            result = CreditResult.model_validate(claims["result"])
            product = _product(claims, context)
            economic_pv = (result.measure.value if result.measure.kind == "credit_pv" else
                           next((item.value for item in result.metrics if (item.key, item.unit) == ("dirty_pv", "EUR")), None))
            side, state = result.side, result.state

        terms = product.terms
        if (result.instrument_type, result.nominal_eur, side, result.valuation_date, result.cutoff) != (
                terms.instrument_type, context.nominal, context.side, context.valuation_date, context.cutoff):
            raise ValueError("Le calcul, la position et l’arrêté ne concordent pas.")
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise ProductError("NATIVE_REPORT_PRICING_INVALID", "Le reçu natif ne porte pas la preuve du calcul attendu.", 422) from exc

    features = _FEATURES[terms.instrument_type]
    if terms.payoff_mode == "scripted":
        # A scripted FRN/IRS can depart from the vanilla cashflows.
        features = ("Flux déterminés par le PayScript de taux figé et ses paramètres effectifs.",
                    "Exposition aux courbes et aux fixings utilisés par le calcul archivé.")

    return {
        "instrument_type": terms.instrument_type, "family": family, "product_id": context.product_id,
        "product_reference": product.reference, "terms_version": context.terms_version,
        "terms_fingerprint": context.terms_fingerprint, "schedule_fingerprint": context.schedule_fingerprint,
        "context_fingerprint": context.fingerprint, "valuation_date": context.valuation_date, "cutoff": context.cutoff,
        "effective_date": terms.effective_date, "maturity_date": terms.maturity_date,
        "nominal_eur": context.nominal, "side": context.side, "measure": result.measure.model_dump(),
        "economic_pv_eur": economic_pv, "market_quality": result.market_quality,
        "position_state": state, "payoff_mode": terms.payoff_mode, "features": features,
    }


def prepare_native_report(claims: dict, body: NativeReportCall) -> NativeReport:
    """Only project authenticated terms, valuation and declared assumptions."""
    fields = _terms_report(claims, body.family)
    if isinstance(body, NativeKidCall):
        return NativeKidPreview(**fields, upfront_eur=body.upfront_eur, entry_cost_eur=body.entry_cost_eur)

    reviews = ["Vérifier l’applicabilité du KID et la concordance avec le marché cible déclaré."]
    if fields["instrument_type"] in ("IRS", "CDS"):
        reviews.append("Qualifier le risque de contrepartie, les appels de marge et les capacités de perte.")
    maturity = fields["maturity_date"]
    if maturity is not None and (maturity - fields["valuation_date"]).days / 365 > body.decision.horizon_years:
        reviews.append("L’horizon déclaré est plus court que l’échéance à l’arrêté. Documenter les possibilités de sortie.")
    if body.decision.channel == "execution_only":
        reviews.append("Documenter l’admissibilité du canal d’exécution pour ce produit.")
    return NativeEmtPreview(**fields, decision=body.decision, matters_to_review=tuple(reviews))
