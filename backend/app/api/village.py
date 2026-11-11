"""GET /api/village — village info for the logged-in admin. Never returns keys."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import as_utc, get_session
from app.models import Village

router = APIRouter(tags=["village"])

AiMode = Literal["demo", "ollama", "anthropic"]
DefaultStructure = Literal["empty", "standard"]


class VillageResponse(BaseModel):
    id: int
    name: str
    chairman_name: str
    timezone: str
    ai_mode: AiMode
    ollama_url: str | None
    default_structure: DefaultStructure
    created_at: datetime
    # True when a key exists in data/.env. The key itself is never returned, and
    # "configured" does not mean "tested": no provider connection is made in M1.
    anthropic_key_configured: bool


def village_response(village: Village) -> VillageResponse:
    return VillageResponse(
        id=village.id,
        name=village.name,
        chairman_name=village.chairman_name,
        timezone=village.timezone,
        ai_mode=village.ai_mode,  # type: ignore[arg-type]
        ollama_url=village.ollama_url,
        default_structure=village.default_structure,  # type: ignore[arg-type]
        created_at=as_utc(village.created_at),  # type: ignore[arg-type]
        anthropic_key_configured=get_settings().anthropic_api_key is not None,
    )


@router.get("/village", response_model=VillageResponse)
def get_village(db: Session = Depends(get_session)) -> VillageResponse:
    village = db.execute(select(Village).order_by(Village.id).limit(1)).scalar_one_or_none()
    if village is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Village not found")
    return village_response(village)
