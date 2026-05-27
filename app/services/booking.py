"""
Бизнес-логика бронирования (F7).

Двухслойная защита от race condition:
  1. Пессимистическая блокировка строки барбера (SELECT ... FOR UPDATE):
     обе конкурентные транзакции последовательно проходят проверку занятости.
  2. UniqueConstraint(barber_id, scheduled_at) на appointments:
     даже если блокировка не сработала, второй INSERT упадёт с IntegrityError,
     которую мы конвертируем в HTTP 409 Conflict.

И слоты доступности (генерация на дату), и создание записи живут здесь —
чтобы один и тот же набор бизнес-правил применялся в обоих сценариях.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ACTIVE_STATUSES,
    Appointment,
    AppointmentStatus,
    BarberProfile,
    Branch,
    Service,
    User,
    UserRole,
)

SLOT_GRANULARITY_MINUTES = 30  # шаг сетки слотов


def _combine(d: date, t: time) -> datetime:
    """Собираем дату и время в aware-datetime (UTC), чтобы корректно сравнивать
    с тем, что приходит из БД (поле DateTime(timezone=True))."""
    return datetime.combine(d, t, tzinfo=timezone.utc)


def _slot_overlaps(
    existing_start: datetime,
    existing_duration: int,
    candidate_start: datetime,
    candidate_duration: int,
) -> bool:
    """Истина, если два интервала [start; start+duration) пересекаются."""
    existing_end = existing_start + timedelta(minutes=existing_duration)
    candidate_end = candidate_start + timedelta(minutes=candidate_duration)
    return existing_start < candidate_end and candidate_start < existing_end


async def list_available_slots(
    db: AsyncSession,
    *,
    branch_id: str,
    service_id: str,
    target_date: date,
    barber_id: str | None,
) -> list[dict]:
    """
    Возвращает все доступные слоты на дату.
    Учитывает: рабочие часы филиала, длительность услуги, занятые слоты,
    привязку барбера к филиалу через FK (исправление "Барбер не найден").
    """
    # 1. Филиал
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if branch is None or not branch.is_active:
        raise HTTPException(status_code=404, detail="Филиал не найден")

    # 2. Услуга
    service = (await db.execute(select(Service).where(Service.id == service_id))).scalar_one_or_none()
    if service is None or not service.is_active:
        raise HTTPException(status_code=404, detail="Услуга не найдена")

    # 3. Барберы филиала. Строгая проверка FK: barber.branch_id == branch_id.
    barbers_q = (
        select(BarberProfile)
        .options(selectinload(BarberProfile.user))
        .join(User, User.id == BarberProfile.user_id)
        .where(
            BarberProfile.branch_id == branch_id,
            User.is_active == True,  # noqa: E712
            User.role == UserRole.BARBER,
        )
    )
    if barber_id is not None:
        barbers_q = barbers_q.where(BarberProfile.user_id == barber_id)

    barbers: Sequence[BarberProfile] = (await db.execute(barbers_q)).scalars().all()
    if barber_id is not None and not barbers:
        # Запрошен конкретный барбер, но он не принадлежит этому филиалу или неактивен.
        raise HTTPException(
            status_code=404,
            detail="Барбер не найден в выбранном филиале",
        )
    if not barbers:
        return []

    # 4. Сетка слотов рабочего дня филиала.
    day_start = _combine(target_date, branch.opens_at)
    day_end = _combine(target_date, branch.closes_at)
    duration = service.duration_minutes

    grid: list[datetime] = []
    cursor = day_start
    while cursor + timedelta(minutes=duration) <= day_end:
        grid.append(cursor)
        cursor += timedelta(minutes=SLOT_GRANULARITY_MINUTES)

    # 5. Все активные записи всех нужных барберов на этот день — одним запросом.
    barber_ids = [b.user_id for b in barbers]
    day_bounds_start = _combine(target_date, time(0, 0))
    day_bounds_end = day_bounds_start + timedelta(days=1)

    busy_rows = (
        await db.execute(
            select(Appointment).where(
                Appointment.barber_id.in_(barber_ids),
                Appointment.status.in_(ACTIVE_STATUSES),
                Appointment.scheduled_at >= day_bounds_start,
                Appointment.scheduled_at < day_bounds_end,
            )
        )
    ).scalars().all()

    busy_by_barber: dict[str, list[Appointment]] = {bid: [] for bid in barber_ids}
    for row in busy_rows:
        busy_by_barber[row.barber_id].append(row)

    # 6. Для каждого барбера и слота — проверка пересечений.
    now = datetime.now(timezone.utc)
    result: list[dict] = []
    for b in barbers:
        for slot_start in grid:
            if slot_start < now:
                continue  # прошедшие слоты не предлагаем
            has_conflict = any(
                _slot_overlaps(busy.scheduled_at, busy.duration_minutes, slot_start, duration)
                for busy in busy_by_barber[b.user_id]
            )
            if has_conflict:
                continue
            result.append(
                {
                    "barber_id": b.user_id,
                    "barber_name": b.user.full_name if b.user else None,
                    "start": slot_start,
                    "duration_minutes": duration,
                }
            )
    # Лог в stdout — помогает отлаживать «почему слотов нет».
    import logging
    logging.getLogger("flatout.booking").info(
        "available slots: branch=%s service=%s date=%s barbers=%d busy_rows=%d slots=%d",
        branch_id, service_id, target_date, len(barbers), len(busy_rows), len(result),
    )
    return result


async def create_appointment_atomically(
    db: AsyncSession,
    *,
    client_id: str,
    branch_id: str,
    barber_id: str,
    service_id: str,
    scheduled_at: datetime,
    client_comment: str | None,
) -> Appointment:
    """
    Создаёт запись с пессимистической блокировкой барбера + страховкой через UniqueConstraint.

    Возвращает созданный Appointment. Бросает HTTPException(409) при конкурентном бронировании.
    """
    # КРИТИЧНО: scheduled_at может прийти naive (из ISO-строки без таймзоны).
    # Приводим к aware UTC ДО любых сравнений, иначе TypeError → 500.
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

    if scheduled_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Нельзя записаться на прошедшее время")

    # 1. Предварительные проверки сущностей (вне блокировки).
    # ВАЖНО: вытаскиваем значения в примитивы ДО возможного rollback'а,
    # потому что rollback инвалидирует ORM-объекты, и обращение к их полям
    # потом ленивым SELECT'ом упадёт с MissingGreenlet в async-контексте.
    branch_row = (
        await db.execute(select(Branch).where(Branch.id == branch_id))
    ).scalar_one_or_none()
    if branch_row is None or not branch_row.is_active:
        raise HTTPException(status_code=404, detail="Филиал не найден")
    branch_opens_at = branch_row.opens_at
    branch_closes_at = branch_row.closes_at

    service_row = (
        await db.execute(select(Service).where(Service.id == service_id))
    ).scalar_one_or_none()
    if service_row is None or not service_row.is_active:
        raise HTTPException(status_code=404, detail="Услуга не найдена")
    service_duration = service_row.duration_minutes
    service_base_price = service_row.base_price

    # Проверка попадания в рабочие часы филиала (всё в UTC, aware).
    slot_end = scheduled_at + timedelta(minutes=service_duration)
    day_open = _combine(scheduled_at.date(), branch_opens_at)
    day_close = _combine(scheduled_at.date(), branch_closes_at)
    if scheduled_at < day_open or slot_end > day_close:
        raise HTTPException(status_code=400, detail="Слот вне рабочих часов филиала")

    # 2. Главный атомарный блок.
    # Закрываем "висящую" неявную транзакцию, открытую SELECT-ами выше (autobegin).
    # Без этого SQLAlchemy ругается "A transaction is already begun on this Session"
    # при попытке db.begin() — нельзя одновременно держать две транзакции.
    if db.in_transaction():
        await db.rollback()

    try:
        async with db.begin():  # явная транзакция → корректный FOR UPDATE.
            # Пессимистическая блокировка строки барбера в barber_profiles.
            barber_profile = (
                await db.execute(
                    select(BarberProfile)
                    .where(BarberProfile.user_id == barber_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()

            if barber_profile is None:
                raise HTTPException(status_code=404, detail="Барбер не найден")
            if barber_profile.branch_id != branch_id:
                raise HTTPException(
                    status_code=400,
                    detail="Барбер не работает в выбранном филиале",
                )
            # Запоминаем коэффициент сразу — он понадобится для расчёта цены.
            barber_multiplier = barber_profile.price_multiplier

            # Проверка активности пользователя-барбера.
            barber_user = (
                await db.execute(select(User).where(User.id == barber_id))
            ).scalar_one_or_none()
            if not barber_user or not barber_user.is_active or barber_user.role != UserRole.BARBER:
                raise HTTPException(status_code=404, detail="Барбер не найден")

            # 3. Проверка пересечения с уже существующими активными записями этого барбера.
            day_bounds_start = _combine(scheduled_at.date(), time(0, 0))
            day_bounds_end = day_bounds_start + timedelta(days=1)
            existing = (
                await db.execute(
                    select(Appointment).where(
                        Appointment.barber_id == barber_id,
                        Appointment.status.in_(ACTIVE_STATUSES),
                        Appointment.scheduled_at >= day_bounds_start,
                        Appointment.scheduled_at < day_bounds_end,
                    )
                )
            ).scalars().all()
            for ex in existing:
                if _slot_overlaps(ex.scheduled_at, ex.duration_minutes, scheduled_at, service_duration):
                    raise HTTPException(status_code=409, detail="Слот уже занят")

            # 4. Создание. final_price фиксируем в момент записи (требование ТЗ).
            # created_at задаём явно (а не полагаемся на server_default), чтобы после
            # commit'а ORM-объект имел заполненное значение, и не нужен был refresh
            # (refresh в async-сессии вне транзакции даёт MissingGreenlet).
            new_apt = Appointment(
                id=str(uuid.uuid4()),
                scheduled_at=scheduled_at,
                status=AppointmentStatus.PENDING,
                service_id=service_id,
                final_price=round(service_base_price * barber_multiplier, 2),
                duration_minutes=service_duration,
                client_id=client_id,
                barber_id=barber_id,
                branch_id=branch_id,
                client_comment=client_comment,
                created_at=datetime.now(timezone.utc),
            )
            db.add(new_apt)
            # commit произойдёт при выходе из db.begin().
    except IntegrityError as exc:
        # Страховочный слой: UniqueConstraint(barber_id, scheduled_at) сработал.
        await db.rollback()
        raise HTTPException(status_code=409, detail="Слот уже занят") from exc

    # refresh уже не нужен — все нужные поля заданы вручную; запрос лишний.
    return new_apt
