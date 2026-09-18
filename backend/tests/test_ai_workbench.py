"""Offline integration checks for the shared AI contract and transports."""
import pytest
from fastapi import HTTPException

from backend.app.core.ai_contract import AiOptions, PromptOverride
from backend.app.services.llm import providers as P
from backend.app.services.llm.workbench import prompt_preview, generate_text
from backend.app.api import amc, emt, pricing


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected network access")
    monkeypatch.setattr(P.httpx, "post", forbidden)
    monkeypatch.setattr(P.httpx, "get", forbidden)
    monkeypatch.setattr(P, "load_key", lambda provider: None)


@pytest.mark.parametrize("module", ["amc", "emt", "product"])
def test_preview_edit_and_generation_share_exact_prompt(module, monkeypatch):
    if module == "amc":
        req = amc.SynthesizeRequest(study_result={"meta": {"product_name": "Etude"}})
        preview, generate = amc.preview_synthesis, amc.synthesize_study
    elif module == "emt":
        req = emt.EmtSynthesizeRequest(product_title="Note", emt_result={"sri": 4})
        preview, generate = emt.preview_synthesis, emt.synthesize_emt
    else:
        req = pricing.ProductAnalysisRequest(resume="MtM 96,30 % — vega 0,03", provider="ollama")
        preview = lambda req, _: pricing.product_analyse_prompt_endpoint(req)
        generate = lambda req, _: pricing.product_analyse_endpoint(req)
    prompt = preview(req, None)
    req.prompt_override = PromptOverride(base_hash=prompt["base_hash"],
        system=prompt["system"] + "\nRédige en trois paragraphes.", user=prompt["user"] + "\nExplique les limites.")
    captured = []
    monkeypatch.setattr(P, "complete_with_metadata", lambda **kwargs: captured.append(kwargs) or P.Completion("Réponse", "resolved-model"))
    result = generate(req, None)
    assert captured[0]["system"] == req.prompt_override.system
    assert captured[0]["user"] == req.prompt_override.user
    assert result["prompt"] == {k: captured[0][k] for k in ("system", "user")}
    assert result["effective_model"] == "resolved-model"
    assert result["prompt_customized"] and result["generation_id"] and result["generated_at"]
    # A changed context must be rejected before reaching the provider.
    if module == "amc": req.study_result["meta"]["product_name"] = "Autre étude"
    elif module == "emt": req.emt_result["sri"] = 6
    else: req.resume = "MtM 97,00 %"
    with pytest.raises(HTTPException, match="contexte du prompt"):
        generate(req, None)
    assert len(captured) == 1


def test_script_refinement_preview_and_custom_prompt_reach_validation(monkeypatch):
    from backend.app.services import llm
    from backend.app.services.llm.prompt import SCRIPT_MARK, EXPLAIN_MARK
    req = pricing.ScriptGenerateRequest(description="Rembourse le nominal", refine=True,
        current_script="AT MATURITY:\n  PAY 0.9", T=1)
    preview = pricing.script_prompt_endpoint(req)
    assert req.current_script in preview["user"]
    captured = []
    raw = f"{SCRIPT_MARK}\nAT MATURITY:\n  PAY 1\n{EXPLAIN_MARK}\nRemboursement du nominal."
    monkeypatch.setattr(llm, "complete_with_metadata", lambda p, m, system, user, **kw:
        captured.append((system, user)) or P.Completion(raw, "test"))
    req.prompt_override = PromptOverride(base_hash=preview["base_hash"], system=preview["system"], user=preview["user"] + "\nSois concis.")
    result = pricing.script_generate_endpoint(req)
    assert captured[0] == (req.prompt_override.system, req.prompt_override.user)
    assert not result["parse_error"]
    assert result["compiles"] is True
    assert result["prompt_customized"]


def test_blank_or_stale_custom_prompts_never_call_provider():
    preview = prompt_preview("Instructions", "Données", "v1")
    for system, digest in [(" ", preview["base_hash"]), ("Instructions", "0" * 64)]:
        with pytest.raises(P.LlmError):
            generate_text(preview, AiOptions(prompt_override=PromptOverride(system=system, user="Demande", base_hash=digest)))


def test_modules_defer_defaults_to_the_shared_catalog():
    from backend.app.services.llm.workbench import connection_options
    requests = [amc.SynthesizeRequest(study_result={}),
                emt.EmtSynthesizeRequest(product_title="Note", emt_result={}),
                pricing.ProductAnalysisRequest(resume="Résumé")]
    for req in requests:
        assert connection_options(req)["provider"] == "ollama"
        assert connection_options(req)["model"] is None


def test_explicit_missing_ollama_model_does_not_silently_switch(monkeypatch):
    monkeypatch.setattr(P, "ollama_models", lambda *a: ["installed:7b"])
    with pytest.raises(P.LlmError, match="plus installé"):
        P.complete_with_metadata("ollama", "missing:14b", "s", "u")
    assert P._modele_effectif(P.PROVIDERS["ollama"], None) == "installed:7b"


@pytest.mark.parametrize("provider", ["ollama", "openai", "anthropic", "claude"])
def test_shared_transport_uses_selected_model_messages_and_connection(provider, monkeypatch):
    calls = []
    response = {"message": {"content": "réponse"}, "choices": [{"message": {"content": "réponse"}}],
                "content": [{"type": "text", "text": "réponse"}]}
    monkeypatch.setattr(P, "ollama_models", lambda *args: ["chosen"])
    monkeypatch.setattr(P, "_post", lambda *args: calls.append(args) or response)
    result = P.complete_with_metadata(provider, "chosen", "système édité", "données éditées",
        ollama_url="http://localhost:11435", api_key="session-secret")
    url, body = calls[0][:2]
    assert body["model"] == result.effective_model == "chosen"
    assert body["messages"][-1]["content"] == "données éditées"
    if provider == "ollama": assert url == "http://localhost:11435/api/chat"
    elif provider == "openai": assert calls[0][2]["Authorization"] == "Bearer session-secret"
    else: assert calls[0][2]["x-api-key"] == "session-secret"


def test_provider_errors_do_not_reflect_response_secrets(monkeypatch):
    import httpx
    monkeypatch.setattr(P.httpx, "post", lambda *a, **kw: httpx.Response(500, text="SECRET"))
    with pytest.raises(P.LlmError) as err:
        P._post("https://provider.example/messages", {})
    assert "SECRET" not in str(err.value)


def test_provenance_uses_model_reported_by_provider(monkeypatch):
    monkeypatch.setattr(P, "_post", lambda *a: {"model": "resolved-version", "choices": [{"message": {"content": "Texte"}}]})
    result = generate_text(prompt_preview("s", "u", "v1"), AiOptions(provider="openai", model="alias", api_key="SECRET"))
    assert result["requested_model"] == "alias"
    assert result["effective_model"] == "resolved-version"
    assert "SECRET" not in str(result)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://name:password@localhost:11434", "http://localhost?key=secret"])
def test_invalid_ollama_connection_is_rejected_before_network(url):
    with pytest.raises(P.LlmError):
        P.complete_with_metadata("ollama", "m", "s", "u", ollama_url=url)
