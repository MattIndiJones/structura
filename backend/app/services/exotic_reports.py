"""Indicative KID figures and EMT review inputs for native exotic pricing."""
from typing import Annotated, Literal

import numpy as np
from pydantic import Field

from ..core.product.models import FrozenModel
from .exotic_valuation import ExoticRatesScenario, ExoticScenario, ExoticValuationError, price_exotic_scenario


KID_METHOD = "indicative_discounted_payoff_distribution"
EMT_METHOD = "desk_target_market_review"


class KidIndicativeCall(FrozenModel):
    report: Literal["kid"]
    receipt: dict = Field(min_length=1)
    upfront_eur: float | None = Field(default=None, gt=0)
    entry_cost_eur: float = Field(default=0, ge=0)


class TargetMarketDecision(FrozenModel):
    client_type: Literal["retail", "professional", "eligible_counterparty"]
    channel: Literal["advice", "management", "execution_only"]
    experience: Literal["informed", "advanced"]
    max_loss_fraction: float = Field(ge=0, le=1)
    tolerance: Literal["medium", "high", "very_high"]
    objective: Literal["income", "growth", "hedging", "diversification"]
    horizon_years: float = Field(gt=0, le=60)
    negative_market: str = Field(min_length=3, max_length=500)


class EmtIndicativeCall(FrozenModel):
    report: Literal["emt"]
    receipt: dict = Field(min_length=1)
    decision: TargetMarketDecision


ReportCall = Annotated[KidIndicativeCall | EmtIndicativeCall, Field(discriminator="report")]


class IndicativePercentile(FrozenModel):
    percentile: Literal[1, 10, 50, 90]
    pv_eur: float
    net_present_difference_eur: float | None


class ExoticKidPreview(FrozenModel):
    report: Literal["kid"] = "kid"
    method: Literal["indicative_discounted_payoff_distribution"] = KID_METHOD
    status: Literal["INDICATIVE_NON_PRIIPS"] = "INDICATIVE_NON_PRIIPS"
    position_id: str
    valuation_date: str
    currency: Literal["EUR"] = "EUR"
    horizon_years: float
    independent_paths: int
    entry_cost_eur: float
    upfront_eur: float | None
    percentiles: tuple[IndicativePercentile, ...]
    required_for_qualification: tuple[str, ...] = (
        "Catégorie, période de détention et hypothèses de liquidité validées",
        "Historique des facteurs ou proxys qualifiés et méthode de stress",
        "Risque de crédit de l’émetteur, coûts réglementaires et contrôle indépendant",
    )


class ExoticEmtPreview(FrozenModel):
    report: Literal["emt"] = "emt"
    method: Literal["desk_target_market_review"] = EMT_METHOD
    status: Literal["INDICATIVE_NON_FINDATEX"] = "INDICATIVE_NON_FINDATEX"
    position_id: str
    valuation_date: str
    currency: Literal["EUR"] = "EUR"
    features: tuple[str, ...]
    decision: TargetMarketDecision
    matters_to_review: tuple[str, ...]


def _exotic_horizon(scenario: ExoticScenario) -> float:
    if isinstance(scenario, ExoticRatesScenario):
        return max(*(flow.payment for flow in scenario.terms.cashflows),
                   *(right.settlement for right in scenario.terms.exercises), 0.0)
    contract = scenario.credit.contract
    return max(contract.maturity_years + contract.default_settlement_delay_years,
               contract.principal_payment_years or 0.0, *(coupon.payment for coupon in contract.coupons))


def _kid_preview(scenario: ExoticScenario, body: KidIndicativeCall) -> ExoticKidPreview:
    horizon = _exotic_horizon(scenario)
    if horizon <= 0:
        raise ExoticValuationError("EXOTIC_KID_HORIZON", "La simulation requiert un horizon contractuel futur.")
    if isinstance(scenario, ExoticRatesScenario):
        settings = scenario.settings.model_copy(update={"antithetic": False})
        calculation = price_exotic_scenario(scenario.model_copy(update={"settings": settings}))
        samples = calculation.independent_pv_eur
    else:
        if scenario.credit.realized is not None:
            raise ExoticValuationError("EXOTIC_KID_REALIZED", "Les scénarios illustratifs portent sur une position avant défaut constaté.")
        settings = scenario.credit.settings.model_copy(update={"estimator": "plain"})
        credit = scenario.credit.model_copy(update={"settings": settings})
        calculation = price_exotic_scenario(scenario.model_copy(update={"credit": credit}), retain_samples=True)
        samples = calculation.dirty_samples

    if samples is None or samples.size < 2:
        raise ExoticValuationError("EXOTIC_KID_SAMPLES", "Les trajectoires indépendantes de payoff ne sont pas disponibles.")
    levels = (1, 10, 50, 90)
    quantiles = np.percentile(samples, levels)
    return ExoticKidPreview(
        position_id=scenario.position_id, valuation_date=scenario.valuation_date.isoformat(),
        horizon_years=horizon, independent_paths=int(samples.size), entry_cost_eur=body.entry_cost_eur,
        upfront_eur=body.upfront_eur,
        percentiles=tuple(IndicativePercentile(
            percentile=level, pv_eur=float(value),
            net_present_difference_eur=None if body.upfront_eur is None else float(value) - body.upfront_eur - body.entry_cost_eur,
        ) for level, value in zip(levels, quantiles, strict=True)),
    )


def _emt_preview(scenario: ExoticScenario, body: EmtIndicativeCall) -> ExoticEmtPreview:
    if isinstance(scenario, ExoticRatesScenario):
        features = ["Exposition à l’actualisation OIS et au funding déclaré"]
        if any(flow.kind != "fixed" for flow in scenario.terms.cashflows):
            features.append("Payoff lié aux taux, au basis et à la volatilité")
        if scenario.terms.exercises:
            features.append("Exercice anticipé contractuel et risque de réinvestissement")
    else:
        features = ["Exposition au défaut et au recouvrement de l’entité de référence"]
        if scenario.credit.contract.kind == "basket_cds":
            features.append("Déclenchement par rang de défaut et dépendance entre références")
        if scenario.credit.contract.kind == "cln":
            features.append("Risque émetteur distinct de l’entité de référence")

    reviews = ["Vérifier cohérence avec le dossier KID ou la conclusion d’applicabilité.",
               "Valider la capacité de perte et le marché cible négatif avec le responsable produit."]
    if body.decision.horizon_years < _exotic_horizon(scenario):
        reviews.append("L’horizon déclaré est plus court que l’échéance économique. Documenter les possibilités de sortie.")
    if body.decision.channel == "execution_only":
        reviews.append("Documenter l’admissibilité du canal d’exécution sur ce produit complexe.")
    return ExoticEmtPreview(
        position_id=scenario.position_id, valuation_date=scenario.valuation_date.isoformat(), features=tuple(features),
        decision=body.decision, matters_to_review=tuple(reviews),
    )


def prepare_exotic_report(scenario: ExoticScenario, body: ReportCall) -> ExoticKidPreview | ExoticEmtPreview:
    if isinstance(body, KidIndicativeCall):
        return _kid_preview(scenario, body)
    return _emt_preview(scenario, body)
