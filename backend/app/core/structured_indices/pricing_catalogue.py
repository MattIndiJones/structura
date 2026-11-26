"""Describe the explicit settings supported by the Athena issue and MTM jobs."""

from typing import Literal

from ..schemas import PricingRequest, UnderlyingParams
from .schemas import (
    ATHENA_FX_CURRENCIES, ATHENA_FX_MODELS, ATHENA_MODEL_PARAMETERS, ATHENA_STEP_DOWN_MODELS, ATHENA_STEP_DOWN_VERSION,
    ATHENA_TEMPLATE_VERSION, PHOENIX_MEMORY_TEMPLATE_VERSION, PHOENIX_MODELS, PHOENIX_TEMPLATE_VERSION,
    QUOTED_PAYOFF_IDS, QUOTED_PAYOFF_MODELS, REVERSE_CONVERTIBLE_MODELS, REVERSE_CONVERTIBLE_TEMPLATE_VERSION,
    AthenaContract, AthenaFxMode, AthenaMarket, AthenaPaymentCurrency, AthenaPricing,
)


class AthenaPricingField(AthenaContract):
    name: str
    label: str
    help: str
    kind: Literal["integer", "boolean", "number"]
    default: int | float | bool
    choices: list[int] | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    scale: int | None = None


class AthenaPricingModel(AthenaContract):
    id: str
    label: str
    fields: list[AthenaPricingField]
    market_fields: list[AthenaPricingField]
    market_curves: list[Literal["dividend_curve", "yield_curve", "funding_curve"]]
    supports_vol_surface: bool = False
    reference_volatility: float | None = None


class AthenaPayoffCapability(AthenaContract):
    id: str
    version: str
    issue_models: list[str]
    mtm_models: list[str]


class AthenaFxCapability(AthenaContract):
    mode: AthenaFxMode
    currencies: list[AthenaPaymentCurrency]
    models: list[str]
    payoffs: list[str]


class AthenaPricingCatalogue(AthenaContract):
    version: Literal["athena-pricing-v1"] = "athena-pricing-v1"
    default_model: str
    models: list[AthenaPricingModel]
    payoffs: list[AthenaPayoffCapability]
    fx_modes: list[AthenaFxCapability]


def _field(name: str, schema: dict, default: int | float | bool, *, scale: int | None = None) -> AthenaPricingField:
    constraints = next((option for option in schema.get("anyOf", []) if option["type"] != "null"), schema)
    return AthenaPricingField(
        name=name, label=schema["title"], help=schema["description"], kind=constraints["type"], default=default,
        choices=constraints.get("enum"), minimum=constraints.get("minimum", constraints.get("exclusiveMinimum")),
        maximum=constraints.get("maximum"), scale=scale,
    )


def athena_pricing_catalogue() -> AthenaPricingCatalogue:
    pricing = AthenaPricing.model_json_schema()["properties"]
    fields = [_field(name, pricing[name], pricing[name]["default"])
              for name in ("n_paths", "seed", "steps_per_year", "antithetic")]
    market = AthenaMarket.model_json_schema()["properties"]
    defaults = {
        "volatility": UnderlyingParams.model_fields["sigma"].default,
        "dividend_yield": UnderlyingParams.model_fields["q"].default,
        "rate": PricingRequest.model_fields["r"].default,
        "funding_spread": PricingRequest.model_fields["funding_spread"].default,
    }
    market_fields = [_field(name, market[name], default, scale=100) for name, default in defaults.items()]
    labels = {"constant": "Volatilité constante (GBM)", "heston": "Heston",
              "sabr": "SABR", "localvol": "Local Vol (Dupire)"}
    return AthenaPricingCatalogue(
        default_model=pricing["model"]["default"],
        fx_modes=[
            AthenaFxCapability(mode=mode, currencies=list(ATHENA_FX_CURRENCIES),
                               models=list(ATHENA_FX_MODELS), payoffs=["athena-sx5e"])
            for mode in ("quanto", "compo")
        ],
        payoffs=[
            AthenaPayoffCapability(id="athena-sx5e", version=ATHENA_TEMPLATE_VERSION,
                                  issue_models=list(ATHENA_MODEL_PARAMETERS), mtm_models=list(ATHENA_MODEL_PARAMETERS)),
            AthenaPayoffCapability(id="athena-step-down-sx5e", version=ATHENA_STEP_DOWN_VERSION,
                                  issue_models=list(ATHENA_STEP_DOWN_MODELS), mtm_models=list(ATHENA_STEP_DOWN_MODELS)),
            AthenaPayoffCapability(id="phoenix-sx5e", version=PHOENIX_TEMPLATE_VERSION,
                                  issue_models=list(PHOENIX_MODELS), mtm_models=list(PHOENIX_MODELS)),
            AthenaPayoffCapability(id="phoenix-memory-sx5e", version=PHOENIX_MEMORY_TEMPLATE_VERSION,
                                  issue_models=list(PHOENIX_MODELS), mtm_models=list(PHOENIX_MODELS)),
            AthenaPayoffCapability(id="reverse-convertible-sx5e", version=REVERSE_CONVERTIBLE_TEMPLATE_VERSION,
                                  issue_models=list(REVERSE_CONVERTIBLE_MODELS),
                                  mtm_models=list(REVERSE_CONVERTIBLE_MODELS)),
            *(AthenaPayoffCapability(id=payoff_id, version=f"{payoff_id}-v1",
                                     issue_models=list(QUOTED_PAYOFF_MODELS), mtm_models=list(QUOTED_PAYOFF_MODELS))
              for payoff_id in QUOTED_PAYOFF_IDS),
        ],
        models=[AthenaPricingModel(
            id=model, label=labels[model],
            fields=[*fields, *[_field(name, pricing[name], UnderlyingParams.model_fields[name].default,
                                      scale=None if name == "kappa" else 100) for name in parameters]],
            market_fields=(market_fields if model in {"constant", "localvol"} else
                           [field for field in market_fields if field.name != "volatility"]),
            market_curves=["dividend_curve", "yield_curve", "funding_curve"],
            supports_vol_surface=model == "localvol",
            reference_volatility=defaults["volatility"],
        ) for model, parameters in ATHENA_MODEL_PARAMETERS.items()],
    )
