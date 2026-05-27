"""
Авторизация и регистрация (F1).

* Пароли хэшируются bcrypt'ом с индивидуальной солью (X3, 152-ФЗ).
* После успешного логина выдаётся JWT с user_id и ролью.
* Регистрация ловит дубликат email через предварительный SELECT и через
  обработку IntegrityError — это гарантирует, что сессия БД не остаётся
  в "сломанном" состоянии при гонке двух регистраций.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models import User, UserRole
from app.schemas import (
    LoginRequest,
    RegisterClientRequest,
    TokenResponse,
    UserPublic,
)

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_client(
    payload: RegisterClientRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Регистрация нового клиента. Сотрудники (barber/manager/admin) создаются
    администратором через отдельный административный эндпоинт (см. F1 в ТЗ).
    """
    # 1. Проактивная проверка дубликата по родительской таблице users.
    existing = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email уже зарегистрирован",
        )

    user = User(
        id=str(uuid.uuid4()),
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        role=UserRole.CLIENT,
        is_active=True,
    )
    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        # 2. Страховочный слой: гонка между SELECT и INSERT.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email уже зарегистрирован",
        ) from None

    await db.refresh(user)
    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        role=user.role,
        full_name=user.full_name,
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Один эндпоинт логина для всех ролей. Различение по таблицам не требуется —
    role хранится в users.
    """
    user = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()

    # Возвращаем единое сообщение для существующего/несуществующего email — против user enumeration.
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )

    token = create_access_token(subject=user.id, role=user.role.value)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        role=user.role,
        full_name=user.full_name,
        email=user.email,
    )


@router.get("/me", response_model=UserPublic)
async def get_me(current: User = Depends(get_current_user)) -> User:
    return current
