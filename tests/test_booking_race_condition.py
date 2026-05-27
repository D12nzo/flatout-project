"""
Контрольный тест для F7 (атомарность бронирования).

Запускает две параллельные транзакции, пытающиеся забронировать один и тот же слот
у одного и того же барбера. Проверяет, что:
  1. Ровно одна запись успешно создаётся в БД.
  2. Вторая транзакция получает HTTPException с кодом 409 Conflict.

Это тест-доказательство, который имеет смысл указать в курсовой при защите.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, time, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import (
    Appointment,
    AppointmentStatus,
    BarberProfile,
    Branch,
    Service,
    User,
    UserRole,
)
from app.services.booking import create_appointment_atomically


pytestmark = pytest.mark.asyncio


async def _setup_minimal_data() -> dict[str, str]:
    """Создаёт филиал, услугу, барбера и двух клиентов. Возвращает их id."""
    async with AsyncSessionLocal() as session:
        branch = Branch(
            id=str(uuid.uuid4()), address="Тестовый филиал", phone="+70000000000",
            opens_at=time(9, 0), closes_at=time(21, 0), work_stations=1, is_active=True,
        )
        service = Service(
            id=str(uuid.uuid4()), name="Тестовая услуга", category="Тест",
            duration_minutes=30, base_price=1000, popularity=0, is_active=True,
        )
        barber_user = User(
            id=str(uuid.uuid4()), full_name="Тест Барбер",
            email=f"b-{uuid.uuid4()}@t.t", phone="+1", hashed_password=hash_password("x"),
            role=UserRole.BARBER, is_active=True,
        )
        client_a = User(
            id=str(uuid.uuid4()), full_name="Клиент A",
            email=f"a-{uuid.uuid4()}@t.t", phone="+2", hashed_password=hash_password("x"),
            role=UserRole.CLIENT, is_active=True,
        )
        client_b = User(
            id=str(uuid.uuid4()), full_name="Клиент B",
            email=f"b-{uuid.uuid4()}@t.t", phone="+3", hashed_password=hash_password("x"),
            role=UserRole.CLIENT, is_active=True,
        )
        session.add_all([branch, service, barber_user, client_a, client_b])
        await session.flush()
        session.add(BarberProfile(user_id=barber_user.id, branch_id=branch.id, price_multiplier=1.0))
        await session.commit()
        return {
            "branch_id": branch.id,
            "service_id": service.id,
            "barber_id": barber_user.id,
            "client_a": client_a.id,
            "client_b": client_b.id,
        }


async def _try_book(ids: dict[str, str], client_id: str, when: datetime) -> str:
    """Возвращает 'ok' или 'conflict'."""
    async with AsyncSessionLocal() as session:
        try:
            await create_appointment_atomically(
                session,
                client_id=client_id,
                branch_id=ids["branch_id"],
                barber_id=ids["barber_id"],
                service_id=ids["service_id"],
                scheduled_at=when,
                client_comment=None,
            )
            return "ok"
        except HTTPException as exc:
            if exc.status_code == 409:
                return "conflict"
            raise


async def test_concurrent_booking_one_wins_one_conflicts() -> None:
    ids = await _setup_minimal_data()
    when = datetime.utcnow().replace(microsecond=0) + timedelta(days=1, hours=2)
    when = when.replace(hour=10, minute=0)

    results = await asyncio.gather(
        _try_book(ids, ids["client_a"], when),
        _try_book(ids, ids["client_b"], when),
    )

    assert sorted(results) == ["conflict", "ok"], f"Ожидали один ok и один conflict, получили {results}"

    # И в БД ровно одна запись.
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Appointment).where(
                    Appointment.barber_id == ids["barber_id"],
                    Appointment.scheduled_at == when,
                    Appointment.status != AppointmentStatus.CANCELLED,
                )
            )
        ).scalars().all()
        assert len(rows) == 1
