"""Prompt preview, context binding and provenance shared by the assistants."""
import hashlib
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from ...core.ai_contract import AiOptions
from . import providers


def prompt_preview(system, user, version, **metadata):
    digest = hashlib.sha256(json.dumps([version, system, user], ensure_ascii=False).encode()).hexdigest()
    return {**metadata, "system": system, "user": user, "prompt_version": version,
            "base_hash": digest, "chars": len(system) + len(user)}


def resolve_prompt(preview, override=None):
    if override is not None:
        if override.base_hash != preview["base_hash"]:
            raise providers.LlmError("Le contexte du prompt a changé. Actualisez le prompt avant de générer.")
        if not override.system.strip() or not override.user.strip():
            raise providers.LlmError("Les deux messages du prompt doivent être renseignés.")
    return {"system": override.system if override else preview["system"],
            "user": override.user if override else preview["user"]}


def connection_options(req):
    """Keep older AMC/EMT clients compatible while using the common transport."""
    provider = "anthropic" if req.provider == "claude" else req.provider
    legacy = "claude" if provider == "anthropic" else provider
    return dict(provider=provider, model=req.model or getattr(req, f"{legacy}_model", None),
                api_key=req.api_key or getattr(req, f"{legacy}_key", ""),
                ollama_url=getattr(req, "url", None) or req.ollama_url)


def generate_text(preview, req: AiOptions, *, temperature=0.3, max_tokens=3000):
    prompt = resolve_prompt(preview, req.prompt_override)
    options = connection_options(req)
    started = time.perf_counter()
    completion = providers.complete_with_metadata(**options, **prompt,
                                                 temperature=temperature, max_tokens=max_tokens)
    return {"text": completion.text, "provider": options["provider"],
            "requested_model": options["model"], "model": completion.effective_model,
            "effective_model": completion.effective_model,
            "generated_at": datetime.now(timezone.utc).isoformat(), "generation_id": str(uuid4()),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "prompt": prompt, "prompt_version": preview["prompt_version"],
            "base_hash": preview["base_hash"],
            "prompt_customized": prompt != {k: preview[k] for k in ("system", "user")}}
