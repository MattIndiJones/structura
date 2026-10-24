"""Validated installation manifests, independent of business database imports."""
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InstallationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    installation_id: UUID
    organization_id: UUID | None = None
    key: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    kind: Literal["organization", "platform"]
    service: Literal["application", "simulation_controller", "portal_redirect", "admin_workbench"] = "application"
    environment: Literal["DEVELOPMENT"] = "DEVELOPMENT"
    data_dir: Path
    port: int = Field(ge=1024, le=65535)
    capabilities: tuple[Literal["request_rfq", "respond_rfq"], ...] = ()
    retention: Literal["UNTIL_EXPLICIT_RESET"] = "UNTIL_EXPLICIT_RESET"
    registry_state: Literal["NOT_CONFIGURED"] = "NOT_CONFIGURED"
    billing_enabled: Literal[False] = False

    @model_validator(mode="after")
    def check_scope(self):
        if (self.kind == "organization") != (self.organization_id is not None):
            raise ValueError("Le type d'installation et son organisation sont incohérents.")
        if self.kind == "platform" and self.capabilities:
            raise ValueError("Le service central ne porte aucune capacité métier privée.")
        if self.service != "application" and self.kind != "platform":
            raise ValueError("Les services de contrôle ne sont pas des installations métier.")
        if not self.data_dir.is_absolute():
            raise ValueError("Le répertoire privé doit être absolu.")
        return self

    def public_descriptor(self):
        return {"installation_id": str(self.installation_id),
                "organization_id": str(self.organization_id) if self.organization_id else None,
                "key": self.key, "name": self.name, "kind": self.kind,
                "environment": self.environment, "capabilities": list(self.capabilities),
                "url": f"http://127.0.0.1:{self.port}",
                "registry_state": self.registry_state, "billing_enabled": False,
                "retention": self.retention}


class DirectoryEntry(BaseModel):
    """Allowlist central metadata; rejects business contents and private paths."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    installation_id: UUID
    organization_id: UUID
    key: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    kind: Literal["organization"]
    environment: Literal["DEVELOPMENT"]
    capabilities: tuple[Literal["request_rfq", "respond_rfq"], ...]
    url: str = Field(pattern=r"^http://127\.0\.0\.1:[0-9]{4,5}$")
    registry_state: Literal["NOT_CONFIGURED"]
    billing_enabled: Literal[False]
    retention: Literal["UNTIL_EXPLICIT_RESET"]


@lru_cache(maxsize=16)
def read_config(path: str) -> InstallationConfig:
    source = Path(path).resolve()
    config = InstallationConfig.model_validate_json(source.read_text(encoding="utf-8"))
    if source.parent != config.data_dir.resolve():
        raise RuntimeError("Le manifeste doit appartenir au répertoire de son installation.")
    return config


def current_config() -> InstallationConfig | None:
    path = os.environ.get("STRUCTURA_INSTALLATION_CONFIG")
    if not path:
        return None
    config = read_config(str(Path(path).resolve()))
    configured_dir = Path(os.environ.get("STRUCTURA_DATA_DIR", config.data_dir)).resolve()
    if configured_dir != config.data_dir.resolve():
        raise RuntimeError("STRUCTURA_DATA_DIR contredit le manifeste d'installation.")
    return config


def credentials(config: InstallationConfig) -> dict[str, str]:
    payload = json.loads((config.data_dir / ".bootstrap_credentials.json").read_text(encoding="utf-8"))
    expected = {"admin"} if config.kind == "platform" else {"superuser", "front", "operations", "controller"}
    if set(payload) != expected or any(not isinstance(p, str) or len(p) < 24 for p in payload.values()):
        raise RuntimeError("Identifiants privés de bootstrap incomplets ou invalides.")
    return payload


def signing_secret(config: InstallationConfig) -> str:
    value = (config.data_dir / ".jwt_secret").read_text(encoding="utf-8").strip()
    if len(value) < 64:
        raise RuntimeError("Clé privée d'installation absente ou invalide ; démarrage refusé.")
    return value
