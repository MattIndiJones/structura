"""Shared router of the deals API; every submodule registers on it."""
from __future__ import annotations
from fastapi import APIRouter
from ..contracts import ContractRoute

router = APIRouter(prefix="/api/deals", tags=["deals"], route_class=ContractRoute)
