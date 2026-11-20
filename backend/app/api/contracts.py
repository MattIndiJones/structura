"""Response contracts of the most used routes (P1-11, A4).

Two of the 458 routes declared what they return. The interface therefore wrote
every call by hand against shapes nobody had written down, and a field renamed
on the server broke a screen without any test noticing.

A route documents its response with `responses=returns(Model)`. That only
feeds the OpenAPI schema — the generated client of the interface is built from
it — and leaves the response itself untouched in production, byte for byte:
declaring a `response_model` on an existing route would filter out every field
the model forgets and turn a wrongly declared type into a 500.

The guarantee comes from the tests. Under STRUCTURA_VALIDATE_RESPONSES=1 (set
by backend/tests/conftest.py and by the end-to-end instance), every 2xx JSON
response of a documented route is checked against its model, unknown fields
refused: a response that drifts from its contract becomes a 500 naming the
field, and the test that produced it fails. The check lives in the route class
(ContractRoute), so it also holds for the many tests that mount a router in an
application of their own.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)


class Contract(BaseModel):
    """A response whose every field is declared: an unknown one is drift."""
    model_config = ConfigDict(extra="forbid")


class OpenContract(BaseModel):
    """A response whose declared fields are checked, the rest left free.

    Kept for the analytical payloads (MtM, calibration, market history) whose
    provenance block is copied from the data source as is: the fields the
    interface reads are declared, the provenance may carry more."""
    model_config = ConfigDict(extra="allow")


def returns(model: Any, status_code: int = 200, description: str = "Réponse") -> dict:
    """`responses=` value documenting what a route returns."""
    return {status_code: {"model": model, "description": description}}


def validating() -> bool:
    return os.environ.get("STRUCTURA_VALIDATE_RESPONSES") == "1"


def documented_model(route: APIRoute) -> Any:
    entry = (route.responses or {}).get(route.status_code or 200) or (route.responses or {}).get(200) or {}
    return entry.get("model")


class ContractRoute(APIRoute):
    """Checks documented responses against their contract when validating()."""

    def get_route_handler(self):
        handler = super().get_route_handler()
        model = documented_model(self)
        if model is None or not validating():
            return handler
        adapter = TypeAdapter(model)
        route = f"{sorted(self.methods or ['?'])[0]} {self.path}"

        async def checked(request):
            response = await handler(request)
            if not (200 <= response.status_code < 300) or not (response.media_type or "").startswith("application/json"):
                return response
            body = getattr(response, "body", None)
            if body is None:        # streamed: nothing to read without consuming it
                return response
            try:
                adapter.validate_python(json.loads(body))
            except ValidationError as error:
                problems = [{"champ": ".".join(str(part) for part in e["loc"]), "erreur": e["msg"]}
                            for e in error.errors(include_url=False)[:10]]
                logger.error("Réponse hors contrat sur %s : %s", route, problems)
                return JSONResponse(status_code=500, content={
                    "detail": f"Réponse hors contrat sur {route}.", "contract_errors": problems})
            return response
        return checked
