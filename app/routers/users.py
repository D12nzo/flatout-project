"""
Управление собственным аккаунтом.

Мягкое удаление (152-ФЗ): персональные данные затираются, флаг is_active = False,
hashed_password забивается заглушкой (логин невозможен).
Связанные appointments НЕ удаляются — final_price и duration_minutes сохраняются для F12.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import UserPublic

router = APIRouter()


@router.get("/me", response_model=UserPublic)
async def read_me(current: User = Depends(get_current_user)) -> User:
    return current


@router.delete("/me")
async def soft_delete_my_account(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Мягкое удаление: затираем PII, отключаем учётку.
    appointments остаются с client_id = текущий ID, но без связанных PII —
    для F12 (расчёт выручки по final_price) этого достаточно.
    """
    current.full_name = None
    current.email = None
    current.phone = None
    # Забиваем хэш строкой, которую невозможно получить из bcrypt.verify — это блокирует логин.
    current.hashed_password = "DELETED"
    current.is_active = False

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
