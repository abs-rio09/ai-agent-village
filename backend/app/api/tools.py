"""GET /api/tools — the central tool registry, read-only."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.agents import CatalogItemOut, tools_out

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("", response_model=list[CatalogItemOut])
def list_tools() -> list[CatalogItemOut]:
    """Every registered tool with its risk level, the permission it needs and whether it is
    built yet. SENSITIVE tools always need the Chairman's approval."""
    return tools_out()
