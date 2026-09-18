"""Shared request contract for all text assistants."""
from pydantic import BaseModel, Field


class PromptOverride(BaseModel):
    base_hash: str = Field(min_length=64, max_length=64)
    system: str = Field(min_length=1, max_length=200000)
    user: str = Field(min_length=1, max_length=400000)


class AiOptions(BaseModel):
    provider: str = "ollama"
    model: str | None = Field(default=None, max_length=160)
    ollama_url: str = Field(default="http://localhost:11434", max_length=500)
    api_key: str = Field(default="", max_length=1000, repr=False)
    prompt_override: PromptOverride | None = None
