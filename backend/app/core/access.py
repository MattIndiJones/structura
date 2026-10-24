"""Separate local business administration from central/technical administration."""
from fastapi import HTTPException


def is_organization_superuser(user) -> bool:
    return (getattr(user, "role", None) == "organization_admin"
            and getattr(user, "is_active", True) and getattr(user, "entity_id", None) is not None)


def is_local_admin(user) -> bool:
    return getattr(user, "role", None) == "admin" or is_organization_superuser(user)


def has_business_role(user, roles) -> bool:
    return getattr(user, "role", None) in roles or is_organization_superuser(user)


def profile(user) -> str:
    return {"organization_admin": "superuser", "user": "front", "ops_maker": "operations",
            "checker": "controller", "admin": "technical_admin"}.get(getattr(user, "role", None), "unknown")


def capabilities(user) -> list[str]:
    grants = {
        "superuser": ["business.read", "business.prepare", "business.price", "sales", "book", "operations.prepare", "operations.validate", "organization.admin", "trading.relationships.manage", "trading.settle"],
        "front": ["business.read", "business.prepare", "business.price", "sales"],
        "operations": ["business.read", "book", "operations.prepare", "trading.settle"],
        "controller": ["business.read", "operations.validate"],
    }
    return grants.get(profile(user), [])


def has_capability(user, capability: str) -> bool:
    from ..hybrid.config import current_config
    config = current_config()
    if not getattr(user, "is_active", True):
        return False
    if config and config.kind != "organization":
        return False
    # The standalone technical administrator predates managed installations.
    return (not config and getattr(user, "role", None) == "admin") or capability in capabilities(user)


def require_capability(user, capability: str):
    if not has_capability(user, capability):
        raise HTTPException(403, "Votre profil ne permet pas cette action.")


def require_booking_permission(user):
    from ..hybrid.config import current_config
    # Preserve standalone Front booking; managed installations use explicit book rights.
    if current_config() is None and user.role == "user" and getattr(user, "is_active", True):
        return
    require_capability(user, "book")


def require_managed_capability(user, capability):
    from ..hybrid.config import current_config
    config = current_config()
    if config and (config.kind != "organization" or capability not in capabilities(user)):
        raise HTTPException(403, "Votre profil ne permet pas cette action dans cette installation.")
