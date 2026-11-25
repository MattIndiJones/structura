"""Versioned inputs for the frozen-market Athena research pricer."""

from datetime import date
from math import isclose
from typing import Annotated, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from ..calendars import add_business_days
from ..schemas import PricingRequest, UnderlyingParams, VolatilitySurfaceParams, validate_term_curve
from ..simulation_grid import GridFrequency


Reference = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=160)]
Level = Annotated[float, Field(strict=True, gt=0, le=1_000_000, allow_inf_nan=False)]
CouponRate = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Rate = Annotated[float, Field(strict=True, ge=-.25, le=.50, allow_inf_nan=False)]
DividendYield = Annotated[float, Field(strict=True, ge=-.25, le=2.0, allow_inf_nan=False)]
Barrier = Annotated[float, Field(strict=True, gt=0, le=3, allow_inf_nan=False)]
FixingLevel = Annotated[float, Field(strict=True, ge=0, le=1_000_000, allow_inf_nan=False)]
ModelNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]
CurvePoint = tuple[ModelNumber, ModelNumber]
Curve = Annotated[tuple[CurvePoint, ...], Field(max_length=64)]
PositiveModelNumber = Annotated[ModelNumber, Field(gt=0)]
Correlation = Annotated[ModelNumber, Field(ge=-1, le=1)]
ATHENA_TEMPLATE_VERSION = "athena-sx5e-v1"
ATHENA_STEP_DOWN_VERSION = "athena-step-down-sx5e-v1"
ATHENA_STEP_DOWN_MODELS = ("constant",)
PHOENIX_TEMPLATE_VERSION = "phoenix-sx5e-v1"
PHOENIX_MEMORY_TEMPLATE_VERSION = "phoenix-memory-sx5e-v1"
PHOENIX_MODELS = ("constant",)
REVERSE_CONVERTIBLE_TEMPLATE_VERSION = "reverse-convertible-sx5e-v1"
REVERSE_CONVERTIBLE_MODELS = ("constant",)
CAPITAL_GUARANTEED = "capital-guaranteed-sx5e"
BOOSTER = "booster-sx5e"
AUTOCALL_GEAR_PUT = "autocall-gear-put-sx5e"
EUROPEAN_PUT = "european-put-sx5e"
EUROPEAN_CALL = "european-call-sx5e"
QUOTED_PAYOFF_MODELS = ("constant",)
QUOTED_PAYOFF_IDS = (CAPITAL_GUARANTEED, BOOSTER, AUTOCALL_GEAR_PUT, EUROPEAN_PUT, EUROPEAN_CALL)
QuoteQuantity = Literal["participation", "redemption_cap", "single_coupon"]
QUOTE_BOUNDS = {"participation": (0., 5.), "redemption_cap": (1., 3.), "single_coupon": (0., .5)}
ATHENA_MODEL_PARAMETERS = {
    "constant": (),
    "heston": ("v0", "kappa", "theta", "xi", "rho_h"),
    "sabr": ("alpha", "beta", "rho", "nu"),
    "localvol": ("skew", "curvature"),
}


class AthenaContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class AthenaObservation(AthenaContract):
    observation_date: date
    payment_date: date


class CapitalGuaranteedPayoff(AthenaContract):
    id: Literal["capital-guaranteed-sx5e"]
    participation_strike: ModelNumber = Field(ge=.5, le=1.5)
    participation: ModelNumber | None = Field(
        None, ge=QUOTE_BOUNDS["participation"][0], le=QUOTE_BOUNDS["participation"][1],
        exclude_if=lambda value: value is None,
    )
    quote_quantities: ClassVar[tuple[QuoteQuantity, ...]] = ("participation",)


class BoosterPayoff(AthenaContract):
    id: Literal["booster-sx5e"]
    participation: ModelNumber | None = Field(
        None, ge=QUOTE_BOUNDS["participation"][0], le=QUOTE_BOUNDS["participation"][1],
        exclude_if=lambda value: value is None,
    )
    redemption_cap: ModelNumber | None = Field(
        None, ge=QUOTE_BOUNDS["redemption_cap"][0], le=QUOTE_BOUNDS["redemption_cap"][1],
        exclude_if=lambda value: value is None,
    )
    quote_quantities: ClassVar[tuple[QuoteQuantity, ...]] = ("participation", "redemption_cap")


class AutocallGearPutPayoff(AthenaContract):
    id: Literal["autocall-gear-put-sx5e"]
    put_strike: ModelNumber = Field(ge=.3, le=1.2)
    gearing: ModelNumber = Field(ge=1, le=5)
    single_coupon: ModelNumber | None = Field(
        None, ge=QUOTE_BOUNDS["single_coupon"][0], le=QUOTE_BOUNDS["single_coupon"][1],
        exclude_if=lambda value: value is None,
    )
    quote_quantities: ClassVar[tuple[QuoteQuantity, ...]] = ("single_coupon",)


class EuropeanOptionPayoff(AthenaContract):
    strike_ratio: Barrier = Field(description="Strike d’exercice, en ratio du fixing initial.")
    quote_quantities: ClassVar[tuple[QuoteQuantity, ...]] = ()


class EuropeanPutPayoff(EuropeanOptionPayoff):
    id: Literal["european-put-sx5e"]


class EuropeanCallPayoff(EuropeanOptionPayoff):
    id: Literal["european-call-sx5e"]


QuotedPayoff = Annotated[
    CapitalGuaranteedPayoff | BoosterPayoff | AutocallGearPutPayoff | EuropeanPutPayoff | EuropeanCallPayoff,
    Field(discriminator="id"),
]


class AthenaTerms(AthenaContract):
    strike_date: date
    observations: tuple[AthenaObservation, ...] = Field(min_length=1, max_length=40)
    calendar_reference: Reference
    observation_months: Literal[3, 6, 12] = 12
    call_barrier: Barrier = 1.0
    call_barriers: tuple[Barrier, ...] | None = Field(
        None, min_length=1, max_length=40, exclude_if=lambda value: value is None,
        description="Seuils de rappel en décimal, ordonnés par constat, dernier constat compris.",
    )
    protection_barrier: Barrier = .60
    coupon_barrier: Barrier | None = Field(
        None, exclude_if=lambda value: value is None,
        description="Seuil de coupon Phoenix, en décimal du fixing initial.",
    )
    coupon_memory: StrictBool | None = Field(
        None, exclude_if=lambda value: value is None,
        description="Active le rattrapage des coupons manqués sur un Phoenix mémoire. Omettre pour les autres payoffs.",
    )
    reverse_convertible: StrictBool | None = Field(
        None, exclude_if=lambda value: value is None,
        description="Active le Reverse Convertible à barrière européenne. Omettre pour les autres payoffs.",
    )
    maturity_years: int | None = Field(
        None, strict=True, ge=1, le=10, exclude_if=lambda value: value is None,
        description="Nombre contractuel d’années appliqué au coupon annuel du Reverse Convertible.",
    )
    payoff: QuotedPayoff | None = Field(
        None, exclude_if=lambda value: value is None,
        description="Termes du Capital garanti, du Booster, de l’autocall Gear Put ou d’une option européenne.",
    )
    settlement_lag: int = Field(2, strict=True, ge=0, le=10)
    underlying: Literal["SX5E"] = "SX5E"
    currency: Literal["EUR"] = "EUR"

    @model_validator(mode="after")
    def validate_terms(self) -> Self:
        days = tuple(row.observation_date for row in self.observations)
        if days[0] <= self.strike_date or days != tuple(sorted(set(days))):
            raise ValueError("Les constats doivent être uniques et ordonnés après le strike.")
        if (days[-1] - self.strike_date).days > 3700 or len(days) * self.observation_months > 120:
            raise ValueError("Le pilote couvre des échéances d'au plus dix ans.")
        if self.payoff is not None:
            self._validate_quoted_payoff()
        elif self.reverse_convertible:
            if self.maturity_years is None or len(days) != 1:
                raise ValueError("Le Reverse Convertible exige une durée en années et un seul constat à maturité.")
            if (self.observation_months != 12 or self.call_barrier != 1.
                    or self.call_barriers is not None or self.coupon_barrier is not None
                    or self.coupon_memory is not None):
                raise ValueError("Seule la barrière de protection est paramétrable sur le Reverse Convertible.")
            if self.protection_barrier > 1:
                raise ValueError("La barrière de protection du Reverse Convertible doit être au plus égale à 100 %.")
        elif self.reverse_convertible is not None or self.maturity_years is not None:
            raise ValueError("Omettre le sélecteur Reverse Convertible et sa durée pour les autres payoffs.")
        elif self.protection_barrier > self.call_barrier:
            raise ValueError("La barrière de protection doit être au plus égale à celle de rappel.")
        if self.coupon_memory is not None and (not self.coupon_memory or self.coupon_barrier is None):
            raise ValueError("Le coupon mémoire exige un seuil de coupon Phoenix et doit être activé.")
        if self.coupon_barrier is not None:
            if self.call_barriers is not None:
                raise ValueError("Le Phoenix utilise une barrière de rappel constante.")
            if self.coupon_barrier > self.call_barrier:
                raise ValueError("La barrière de coupon doit être au plus égale à celle de rappel.")
        if self.call_barriers is not None:
            if len(self.call_barriers) != len(days):
                raise ValueError("Une barrière de rappel doit être définie par constat.")
            if self.call_barriers[0] != self.call_barrier:
                raise ValueError("La première barrière datée doit correspondre à la barrière de rappel initiale.")
            if any(left < right for left, right in zip(self.call_barriers, self.call_barriers[1:])):
                raise ValueError("La grille des barrières de rappel doit être non croissante.")
            if self.protection_barrier > self.call_barriers[-1]:
                raise ValueError("La barrière de protection doit être au plus égale à celle du dernier constat de rappel.")
        for event in self.observations:
            if event.payment_date != add_business_days(event.observation_date, self.settlement_lag, "TARGET"):
                raise ValueError(f"Règlement TARGET incompatible avec le constat du {event.observation_date}.")
        return self

    def _validate_quoted_payoff(self) -> None:
        if any(term is not None for term in (
            self.reverse_convertible, self.maturity_years, self.coupon_barrier, self.coupon_memory, self.call_barriers,
        )) or self.protection_barrier != .60:
            raise ValueError("Termes historiques incompatibles avec le payoff sélectionné.")
        if not self.has_autocall:
            if len(self.observations) != 1 or self.observation_months != 12 or self.call_barrier != 1.:
                raise ValueError("Ce payoff exige un seul constat à échéance et aucun seuil de rappel.")
        elif not .8 <= self.call_barrier <= 1.2 or self.payoff.put_strike > self.call_barrier:
            raise ValueError("Le seuil de rappel Gear Put doit être de 80 à 120 % et au moins égal au strike du put.")

    @property
    def has_participation(self) -> bool:
        return isinstance(self.payoff, (CapitalGuaranteedPayoff, BoosterPayoff))

    @property
    def has_option_payoff(self) -> bool:
        return isinstance(self.payoff, EuropeanOptionPayoff)

    @property
    def has_autocall(self) -> bool:
        return not (self.reverse_convertible or self.has_participation or self.has_option_payoff)

    @property
    def has_terminal_protection(self) -> bool:
        return not (self.has_participation or self.has_option_payoff)

    @property
    def effective_protection_barrier(self) -> float:
        if isinstance(self.payoff, AutocallGearPutPayoff):
            return self.payoff.put_strike
        return self.protection_barrier

    @property
    def effective_call_barriers(self) -> tuple[float, ...]:
        if self.call_barriers is not None:
            return self.call_barriers
        return (self.call_barrier,) * len(self.observations)

    @property
    def payoff_version(self) -> str:
        if self.payoff is not None:
            return f"{self.payoff.id}-v1"
        if self.reverse_convertible:
            return REVERSE_CONVERTIBLE_TEMPLATE_VERSION
        if self.coupon_memory:
            return PHOENIX_MEMORY_TEMPLATE_VERSION
        if self.coupon_barrier is not None:
            return PHOENIX_TEMPLATE_VERSION
        return ATHENA_STEP_DOWN_VERSION if self.call_barriers is not None else ATHENA_TEMPLATE_VERSION

    def validate_pricing(self, pricing: "AthenaPricing") -> None:
        if self.payoff is not None and pricing.model not in QUOTED_PAYOFF_MODELS:
            raise ValueError("Le modèle demandé n’est pas qualifié pour le payoff sélectionné.")
        if self.reverse_convertible and pricing.model not in REVERSE_CONVERTIBLE_MODELS:
            raise ValueError("Le modèle demandé n'est pas qualifié pour le Reverse Convertible.")
        if self.call_barriers is not None and pricing.model not in ATHENA_STEP_DOWN_MODELS:
            raise ValueError("Le modèle demandé n'est pas qualifié pour l'Athena dégressif.")
        if self.coupon_barrier is not None and pricing.model not in PHOENIX_MODELS:
            raise ValueError("Le modèle demandé n'est pas qualifié pour le Phoenix.")


class AthenaVintage(AthenaContract):
    note_id: Reference
    terms: AthenaTerms
    initial_fixing: Level
    initial_fixing_reference: Reference
    annual_coupon: CouponRate | None = Field(None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_completed_terms(self) -> Self:
        payoff = self.terms.payoff
        if payoff is None:
            if self.annual_coupon is None:
                raise ValueError("Le coupon annuel du millésime est requis.")
        elif self.annual_coupon is not None or any(getattr(payoff, key) is None for key in payoff.quote_quantities):
            raise ValueError("Le millésime exige des termes de payoff définitifs et sans coupon annuel.")
        return self


class AthenaFixing(AthenaContract):
    day: date
    spot: FixingLevel
    reference: Reference


class AthenaMarket(AthenaContract):
    as_of: date
    reference: Reference
    spot: Level
    rate: Rate = Field(title="Taux sans risque (%)", description="Taux plat qui alimente le drift et l’actualisation.")
    volatility: float = Field(
        strict=True, ge=0, le=2, allow_inf_nan=False, title="Volatilité annuelle (%)",
        description="Volatilité constante appliquée à la diffusion du SX5E.",
    )
    dividend_yield: DividendYield = Field(
        title="Dividendes (%/an)", description="Rendement continu des dividendes utilisé pour le forward du SX5E.",
    )
    funding_spread: Rate = Field(
        title="Spread de funding (%)", description="Spread émetteur appliqué uniquement à l’actualisation.",
    )
    dividend_curve: Curve | None = Field(default=None, exclude_if=lambda value: value is None)
    yield_curve: Curve | None = Field(default=None, exclude_if=lambda value: value is None)
    funding_curve: Curve | None = Field(default=None, exclude_if=lambda value: value is None)
    vol_surface: VolatilitySurfaceParams | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_curves(self) -> Self:
        if self.dividend_curve:
            UnderlyingParams.validate_dividend_curve(self.dividend_curve)
            if not isclose(self.dividend_yield, self.dividend_curve[0][1], abs_tol=1e-12, rel_tol=0):
                raise ValueError("Le dividende plat doit correspondre au premier bucket de la courbe.")
        if self.yield_curve:
            validate_term_curve(self.yield_curve, "courbe de taux")
        if self.funding_curve:
            validate_term_curve(self.funding_curve, "courbe de funding")
        return self

    def validate_model(self, pricing: "AthenaPricing") -> None:
        if self.vol_surface is not None:
            if pricing.model != "localvol":
                raise ValueError("La surface SSVI Athena est utilisable avec le modèle Local Vol.")
            if pricing.skew or pricing.curvature:
                raise ValueError("La surface SSVI remplace le skew et la courbure manuels.")


class AthenaPricing(AthenaContract):
    model: Literal["constant", "heston", "sabr", "localvol"] = PricingRequest.model_fields["model"].default
    n_paths: int = Field(
        PricingRequest.model_fields["N"].default, strict=True, ge=2, le=50_000, title="Tirages Monte Carlo",
        description="Nombre de tirages indépendants. Avec les antithétiques, chaque tirage forme une paire de trajectoires.",
    )
    seed: int = Field(
        PricingRequest.model_fields["seed"].default, strict=True, ge=0, le=2**32 - 1, title="Graine Monte Carlo",
        description="Graine conservée avec le calcul pour reproduire les mêmes tirages.",
    )
    steps_per_year: GridFrequency = Field(
        PricingRequest.model_fields["steps_per_year"].default, title="Grille de diffusion (pas/an)",
        description="Nombre de pas de simulation par an. Une grille fine augmente le coût de calcul.",
    )
    antithetic: bool = Field(
        PricingRequest.model_fields["antithetic"].default, strict=True, title="Variantes antithétiques",
        description="Associe à chaque trajectoire son opposée pour réduire la variance de l’estimation.",
    )

    v0: PositiveModelNumber | None = Field(
        None, title="Variance initiale (%)", description="Variance initiale du processus Heston.",
        exclude_if=lambda value: value is None,
    )
    kappa: PositiveModelNumber | None = Field(
        None, title="Retour à la moyenne (par an)", description="Vitesse annuelle de retour de la variance vers son niveau d’équilibre.",
        exclude_if=lambda value: value is None,
    )
    theta: PositiveModelNumber | None = Field(
        None, title="Variance de long terme (%)", description="Niveau d’équilibre de la variance Heston.",
        exclude_if=lambda value: value is None,
    )
    xi: PositiveModelNumber | None = Field(
        None, title="Volatilité de la variance (%)", description="Volatilité du processus de variance Heston.",
        exclude_if=lambda value: value is None,
    )
    rho_h: Correlation | None = Field(
        None, title="Corrélation spot/variance (%)", description="Corrélation des chocs de spot et de variance Heston.",
        exclude_if=lambda value: value is None,
    )
    alpha: PositiveModelNumber | None = Field(
        None, title="Alpha (%)", description="Niveau initial de volatilité SABR.",
        exclude_if=lambda value: value is None,
    )
    beta: Annotated[ModelNumber, Field(ge=0, le=1)] | None = Field(
        None, title="Bêta (%)", description="Élasticité de la diffusion SABR au niveau normalisé du sous-jacent.",
        exclude_if=lambda value: value is None,
    )
    rho: Correlation | None = Field(
        None, title="Corrélation SABR (%)", description="Corrélation des chocs de spot et de volatilité SABR.",
        exclude_if=lambda value: value is None,
    )
    nu: Annotated[ModelNumber, Field(ge=0)] | None = Field(
        None, title="Volatilité de la volatilité (%)", description="Volatilité du facteur de volatilité SABR.",
        exclude_if=lambda value: value is None,
    )
    skew: ModelNumber | None = Field(
        None, title="Skew manuel (%)", description="Pente du smile local en l’absence de surface SSVI.",
        exclude_if=lambda value: value is None,
    )
    curvature: ModelNumber | None = Field(
        None, title="Courbure manuelle (%)", description="Courbure du smile local en l’absence de surface SSVI.",
        exclude_if=lambda value: value is None,
    )

    @model_validator(mode="before")
    @classmethod
    def set_model_defaults(cls, raw):
        if not isinstance(raw, dict):
            return raw
        model = raw.get("model", "constant")
        if not isinstance(model, str) or model not in ATHENA_MODEL_PARAMETERS:
            return raw
        selected = ATHENA_MODEL_PARAMETERS[model]
        defaults = {name: UnderlyingParams.model_fields[name].default for name in selected if raw.get(name) is None}
        return {**raw, **defaults} if defaults else raw

    @model_validator(mode="after")
    def validate_model_parameters(self) -> Self:
        selected = ATHENA_MODEL_PARAMETERS[self.model]
        unknown = [name for fields in ATHENA_MODEL_PARAMETERS.values() for name in fields
                   if name not in selected and getattr(self, name) is not None]
        if unknown:
            raise ValueError(f"Paramètres non utilisés par le modèle {self.model} : {', '.join(unknown)}.")
        return self

    def underlying_parameters(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in ATHENA_MODEL_PARAMETERS[self.model]}

    def check_size(self, as_of: date, maturity: date) -> None:
        estimated_steps = max(0, ((maturity - as_of).days * self.steps_per_year + 364) // 365)
        if self.n_paths * estimated_steps > 8_000_000:
            raise ValueError("La grille et le nombre de trajectoires dépassent le budget par valorisation.")


class AthenaFixedCoupon(AthenaContract):
    mode: Literal["fixed"]
    fixed_coupon: CouponRate


class AthenaSolvedCoupon(AthenaContract):
    mode: Literal["solve_to_target"]
    target_price: Level
    min_coupon: CouponRate
    max_coupon: CouponRate
    price_tolerance: float = Field(.01, strict=True, gt=0, le=.01, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.max_coupon < self.min_coupon:
            raise ValueError("La borne de coupon maximale doit être au moins égale à la borne minimale.")
        return self


AthenaCoupon = Annotated[AthenaFixedCoupon | AthenaSolvedCoupon, Field(discriminator="mode")]


class AthenaFixedQuote(AthenaContract):
    mode: Literal["fixed"]


class AthenaSolvedQuote(AthenaContract):
    mode: Literal["solve_to_target"]
    quantity: QuoteQuantity
    target_price: Level
    minimum: ModelNumber
    maximum: ModelNumber
    price_tolerance: float = Field(.01, strict=True, gt=0, le=.01, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        floor, cap = QUOTE_BOUNDS[self.quantity]
        if not floor <= self.minimum <= self.maximum <= cap:
            raise ValueError("Les bornes de résolution sont incompatibles avec la quantité à résoudre.")
        return self


AthenaQuote = Annotated[AthenaFixedQuote | AthenaSolvedQuote, Field(discriminator="mode")]


class AthenaIssueRequest(AthenaContract):
    note_id: Reference
    terms: AthenaTerms
    market: AthenaMarket
    pricing: AthenaPricing
    coupon: AthenaCoupon | None = Field(None, exclude_if=lambda value: value is None)
    quote: AthenaQuote | None = Field(None, exclude_if=lambda value: value is None)
    initial_fixing: Level
    initial_fixing_reference: Reference

    @model_validator(mode="after")
    def validate_issue(self) -> Self:
        if self.market.as_of != self.terms.strike_date:
            raise ValueError("L'instantané d'émission doit être daté du strike.")
        self._validate_issue_economics()
        self.terms.validate_pricing(self.pricing)
        self.market.validate_model(self.pricing)
        self.pricing.check_size(self.market.as_of, self.terms.observations[-1].observation_date)
        return self


    def _validate_issue_economics(self) -> None:
        payoff = self.terms.payoff
        if payoff is None:
            if self.coupon is None or self.quote is not None:
                raise ValueError("Ce payoff exige un coupon annuel et aucun autre réglage de cotation.")
            return
        if self.quote is None or self.coupon is not None:
            raise ValueError("Ce payoff exige des réglages de cotation sans coupon annuel.")
        missing = {key for key in payoff.quote_quantities if getattr(payoff, key) is None}
        if isinstance(self.quote, AthenaSolvedQuote):
            if missing != {self.quote.quantity}:
                raise ValueError("Omettre uniquement la quantité à résoudre dans les termes du payoff.")
            if self.quote.quantity == "redemption_cap" and payoff.participation < .005:
                raise ValueError("La participation imposée doit être d’au moins 0,5 % pour résoudre le cap.")
        elif missing:
            raise ValueError("Tous les paramètres du payoff doivent être renseignés pour une cotation fixe.")


def _check_fixing_dates(vintage: AthenaVintage, as_of: date, fixings: tuple[AthenaFixing, ...]) -> None:
    if as_of < vintage.terms.strike_date:
        raise ValueError("La date de valorisation précède le strike.")
    days = [row.day for row in fixings]
    eligible_days = {row.observation_date for row in vintage.terms.observations if row.observation_date <= as_of}
    if len(set(days)) != len(days) or not set(days) <= eligible_days:
        raise ValueError("Fournir des fixings uniques, datés des constats échus.")


class AthenaLifecycleRequest(AthenaContract):
    vintage: AthenaVintage
    as_of: date
    fixings: tuple[AthenaFixing, ...] = Field(max_length=40)

    @model_validator(mode="after")
    def validate_fixings(self) -> Self:
        _check_fixing_dates(self.vintage, self.as_of, self.fixings)
        return self


class AthenaMarkRequest(AthenaContract):
    vintage: AthenaVintage
    market: AthenaMarket
    pricing: AthenaPricing
    fixings: tuple[AthenaFixing, ...] = Field(max_length=40)

    @model_validator(mode="after")
    def validate_mark(self) -> Self:
        _check_fixing_dates(self.vintage, self.market.as_of, self.fixings)
        self.vintage.terms.validate_pricing(self.pricing)
        self.market.validate_model(self.pricing)
        self.pricing.check_size(self.market.as_of, self.vintage.terms.observations[-1].observation_date)
        return self
