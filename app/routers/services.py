"""Услуги (F3)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Service
from app.schemas import ServicePublic

router = APIRouter()


@router.get("/", response_model=list[ServicePublic])
async def list_services(db: AsyncSession = Depends(get_db)) -> list[Service]:
    rows = (await db.execute(select(Service).where(Service.is_active == True))).scalars().all()  # noqa: E712
    return list(rows)


@router.get("/{service_id}", response_model=ServicePublic)
async def get_service(service_id: str, db: AsyncSession = Depends(get_db)) -> Service:
    service = (await db.execute(select(Service).where(Service.id == service_id))).scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    return service
