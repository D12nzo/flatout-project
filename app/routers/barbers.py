"""Список барберов (F4) с фильтрами по филиалу и услуге."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import BarberProfile, User, UserRole
from app.schemas import BarberPublic

router = APIRouter()


@router.get("/", response_model=list[BarberPublic])
async def list_barbers(
    db: AsyncSession = Depends(get_db),
    branch_id: str | None = None,
) -> list[BarberPublic]:
    """
    Возвращает только активных барберов. Если задан branch_id — строго по FK.
    """
    q = (
        select(BarberProfile)
        .options(selectinload(BarberProfile.user))
        .join(User, User.id == BarberProfile.user_id)
        .where(User.is_active == True, User.role == UserRole.BARBER)  # noqa: E712
    )
    if branch_id is not None:
        q = q.where(BarberProfile.branch_id == branch_id)

    rows = (await db.execute(q)).scalars().all()
    return [
        BarberPublic(
            id=b.user_id,
            full_name=b.user.full_name if b.user else None,
            branch_id=b.branch_id,
            specialization=b.specialization,
            rating=b.rating,
            price_multiplier=b.price_multiplier,
            work_status=b.work_status,
        )
        for b in rows
    ]
