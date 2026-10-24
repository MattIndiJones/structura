"""OpenAI decisions for fictitious workshop campaigns only.

The existing LLM key loader is shared with Structura's other AI features. This
adapter deliberately does not reuse their free-form completions: workshop
decisions need cancellation, JSON validation, and per-campaign usage accounting.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time

import httpx

from ..llm.keys import load_key


# Standard short-context prices in USD per million tokens, as of 2026-10-14.
# Pinning a catalog makes both model selection and the cost estimate reviewable.
MODELS = {
    "gpt-5-nano": {"label": "GPT-5 nano · tarif minimal (déprécié)", "input": 0.05, "output": 0.40, "deprecated": True},
    "gpt-6-luna": {"label": "GPT-6 Luna · économique recommandé", "input": 0.10, "output": 0.50, "deprecated": False},
    "gpt-6-sol": {"label": "GPT-6 Sol · analyse approfondie", "input": 2.00, "output": 10.00, "deprecated": False},
    "gpt-6.1-sol": {"label": "GPT-6.1 Sol · analyse approfondie", "input": 4.00, "output": 20.00, "deprecated": False},
}

DEFAULT_MODEL = "gpt-6-luna"
MAX_OUTPUT_TOKENS = 4000
API_URL = "https://api.openai.com/v1/responses"


class ModelUnavailable(ValueError):
    def __init__(self, message: str, metadata: dict | None = None):
        super().__init__(message)
        self.metadata = metadata or {}


class BudgetReached(ModelUnavailable):
    """No request was sent because the campaign's local cost cap was reached."""


class IncompleteOutput(ValueError):
    """A paid response reached its output limit; retry the decision, not the provider."""

    def __init__(self, message: str, metadata: dict):
        super().__init__(message)
        self.metadata = metadata


def price(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = MODELS[model]
    return round((input_tokens * rate["input"] + output_tokens * rate["output"]) / 1_000_000, 8)


def _content(data: dict) -> str:
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    return part.get("text") or ""
                if part.get("type") == "refusal":
                    raise ModelUnavailable("Le modèle a refusé cette décision ; aucune action métier n'a été exécutée.")
    return ""


def _request(body: dict, key: str, timeout: int, cancelled=None) -> dict:
    async def run():
        async with httpx.AsyncClient(timeout=timeout) as client:
            if cancelled and cancelled():
                raise asyncio.CancelledError()
            pending = asyncio.create_task(client.post(API_URL, json=body, headers={"Authorization": f"Bearer {key}"}))
            try:
                while True:
                    completed, _ = await asyncio.wait({pending}, timeout=.2)
                    if cancelled and cancelled():
                        raise asyncio.CancelledError()
                    if completed:
                        response = await pending
                        if response.status_code >= 400:
                            code = (response.json().get("error") or {}).get("code") if response.headers.get("content-type", "").startswith("application/json") else None
                            if response.status_code in (401, 403):
                                raise ModelUnavailable("Clé OpenAI refusée dans ce processus.")
                            if response.status_code == 429:
                                raise ModelUnavailable("Limite ou crédits API OpenAI atteints ; campagne à interrompre.", {"provider_error": code or "rate_limit"})
                            raise ModelUnavailable(f"OpenAI a refusé la décision (HTTP {response.status_code}, code {code or 'non précisé'}).")
                        return response.json()
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    def run_sync():
        return asyncio.run(run())

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return run_sync()
    # Keep Playwright's synchronous browser operations on their original thread.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="Structura OpenAI HTTP") as executor:
        return executor.submit(run_sync).result()


def _decision_schema(action_schema: dict) -> dict:
    """Wrap the existing role-scoped tool schema for strict Responses output."""
    choices = []
    for original in action_schema.get("anyOf", []):
        branch = json.loads(json.dumps(original))
        tool = branch["properties"]["tool"]["const"]
        if tool == "api":
            # Arbitrary API request bodies cannot satisfy strict schema rules.
            # Native workshop operations remain available as dedicated tools.
            continue
        branch["properties"]["tool"] = {"type": "string", "enum": [tool]}
        args = branch["properties"]["args"]
        args["properties"] = {key: value for key, value in args["properties"].items()
                              if key in args["required"]}
        choices.append(branch)
    if not choices:
        raise ModelUnavailable("Aucune opération de l'agent ne peut être décrite au modèle.")
    return {"type": "object", "properties": {"decision": {"anyOf": choices}},
            "required": ["decision"], "additionalProperties": False}


def response(config: dict, messages: list[dict], timeout: int, cancelled=None,
             usage: dict | None = None, action_schema: dict | None = None) -> dict:
    model = config["model"]
    if model not in MODELS:
        raise ModelUnavailable("Modèle OpenAI non proposé pour la simulation.")
    key = load_key("openai")
    if not key:
        raise ModelUnavailable("Aucune clé OpenAI accessible au contrôleur de simulation.")
    max_cost = float(config.get("max_ai_cost_usd", 5))
    spent = float((usage or {}).get("model_cost_usd", 0))
    # UTF-8 bytes conservatively bound normal text token counts; reserve the
    # full allowed output before sending to keep an individual run near its cap.
    input_ceiling = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 100
    reservation = price(model, input_ceiling, MAX_OUTPUT_TOKENS)
    if spent + reservation > max_cost:
        raise BudgetReached("Plafond IA de la campagne atteint avant ce nouvel appel.")
    decision_schema = _decision_schema(action_schema or {"anyOf": [
        {"type": "object", "properties": {"tool": {"const": "wait"},
            "args": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "reason": {"type": "string"}},
         "required": ["tool", "args", "reason"], "additionalProperties": False}]})
    body = {"model": model, "input": messages, "store": False,
            "text": {"format": {"type": "json_schema", "name": "workshop_decision",
                                "strict": True, "schema": decision_schema}},
            "max_output_tokens": MAX_OUTPUT_TOKENS}
    if model in {"gpt-6-luna", "gpt-6-sol"}:
        body["reasoning"] = {"effort": "none"}
    elif model == "gpt-6.1-sol":
        body["reasoning"] = {"effort": "low"}
    started = time.monotonic()
    try:
        data = _request(body, key, timeout, cancelled)
    except asyncio.CancelledError:
        raise
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise ModelUnavailable("OpenAI n'a pas répondu dans le délai ; aucune action métier n'a été exécutée.",
                               {'provider':'openai','cost_unknown':True}) from exc
    token_usage = data.get("usage") or {}
    input_tokens = int(token_usage.get("input_tokens") or 0)
    output_tokens = int(token_usage.get("output_tokens") or 0)
    metadata = {"model": data.get("model") or model, "provider": "openai",
                "seconds": round(time.monotonic() - started, 3),
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "reasoning_tokens": int((token_usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0),
                "cost_usd": price(model, input_tokens, output_tokens) if token_usage else None,
                "cost_unknown": not bool(token_usage)}
    if data.get("status") == "incomplete" and (data.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
        raise IncompleteOutput("Réponse OpenAI tronquée par la limite de sortie ; aucune action métier n'a été exécutée.", metadata)
    if data.get("status") != "completed":
        raise ModelUnavailable("Réponse OpenAI incomplète ; aucune action métier n'a été exécutée.", metadata)
    try:
        text = _content(data)
    except ModelUnavailable as exc:
        exc.metadata = metadata
        raise
    if not text:
        raise ModelUnavailable("Réponse OpenAI vide ; aucune action métier n'a été exécutée.", metadata)
    return {"message": {"content": text}, "model": metadata["model"], "done_reason": "stop", "metadata": metadata}
