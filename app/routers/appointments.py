"""
Записи (F7, F8, F9, F11, F13).
"""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_roles
from app.database import get_db
from app.models import (
    ACTIVE_STATUSES,
    Appointment,
    AppointmentStatus,
    Branch,
    Service,
    User,
    UserRole,
)
from app.schemas import (
    AppointmentCreateRequest,
    AppointmentDetailed,
    AppointmentPublic,
    BarberNoteUpdate,
    SlotPublic,
    SlotsResponse,
)
from app.services.booking import (
    create_appointment_atomically,
    list_available_slots,
)
from app.services.notifications import (
    send_appointment_cancelled_email,
    send_appointment_confirmation_email,
)

router = APIRouter()


# ---------- Доступные слоты ----------


@router.get("/available", response_model=SlotsResponse)
async def get_available_slots(
    branch_id: str = Query(...),
    service_id: str = Query(...),
    target_date: date = Query(...),
    barber_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> SlotsResponse:
    """
    Возвращает доступные слоты по выбранным филиалу, услуге и (опционально) барберу.
    Учитывает рабочие часы филиала, длительность услуги, занятые слоты,
    строгую связь Barber → Branch через FK (исправление "Барбер не найден").
    """
    raw_slots = await list_available_slots(
        db,
        branch_id=branch_id,
        service_id=service_id,
        target_date=target_date,
        barber_id=barber_id,
    )
    return SlotsResponse(
        target_date=target_date,
        branch_id=branch_id,
        service_id=service_id,
        slots=[SlotPublic(**s) for s in raw_slots],
    )


# ---------- Создание записи (F7) ----------


@router.post("/", response_model=AppointmentPublic, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreateRequest,
    current: User = Depends(require_roles(UserRole.CLIENT)),
    db: AsyncSession = Depends(get_db),
) -> AppointmentPublic:
    """
    Создание записи клиентом. client_id берётся из JWT — клиент не может записать другого.
    """
    # ВАЖНО: вытаскиваем поля юзера ДО create_appointment_atomically.
    # Внутри неё делается db.rollback() — он протухивает все ORM-объекты сессии,
    # включая current (загружен в той же сессии через require_roles).
    # Если читать current.email/full_name ПОСЛЕ — SQLAlchemy попытается лениво
    # перезагрузить их и упадёт с MissingGreenlet в async-контексте.
    current_id = current.id
    current_email = current.email
    current_name = current.full_name

    apt = await create_appointment_atomically(
        db,
        client_id=current_id,
        branch_id=payload.branch_id,
        barber_id=payload.barber_id,
        service_id=payload.service_id,
        scheduled_at=payload.scheduled_at,
        client_comment=payload.client_comment,
    )

    # СНАЧАЛА собираем ответ из локальных полей apt (они в памяти после
    # expire_on_commit=False) — это самый безопасный путь, никаких ленивых
    # подгрузок не будет.
    response = AppointmentPublic(
        id=apt.id,
        scheduled_at=apt.scheduled_at,
        status=apt.status,
        service_id=apt.service_id,
        final_price=apt.final_price,
        duration_minutes=apt.duration_minutes,
        client_id=apt.client_id,
        barber_id=apt.barber_id,
        branch_id=apt.branch_id,
        client_comment=apt.client_comment,
        barber_note=apt.barber_note,
        created_at=apt.created_at,
    )

    # F13: email-уведомление о создании записи (заглушка).
    # Запускаем fire-and-forget с уже готовыми примитивами — никаких ORM-объектов
    # в замыкании, чтобы избежать MissingGreenlet после закрытия сессии.
    apt_scheduled = apt.scheduled_at
    apt_price = apt.final_price

    async def _notify() -> None:
        # Открываем СВОЮ сессию для подгрузки имён — основная уже может закрыться
        # к моменту выполнения задачи.
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            try:
                br = (await s.execute(select(Branch).where(Branch.id == response.branch_id))).scalar_one_or_none()
                sv = (await s.execute(select(Service).where(Service.id == response.service_id))).scalar_one_or_none()
                bu = (await s.execute(select(User).where(User.id == response.barber_id))).scalar_one_or_none()
            except Exception:
                return
        await send_appointment_confirmation_email(
            to_email=current_email,
            client_name=current_name,
            scheduled_at=apt_scheduled,
            service_name=sv.name if sv else "услуга",
            branch_address=br.address if br else "—",
            barber_name=bu.full_name if bu else None,
            final_price=apt_price,
        )

    asyncio.create_task(_notify())

    return response


# ---------- Просмотр записей ----------


@router.get("/me", response_model=list[AppointmentDetailed])
async def list_my_appointments(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    upcoming_only: bool = Query(default=False),
) -> list[AppointmentDetailed]:
    """
    Возвращает записи в зависимости от роли:
    - CLIENT  → его собственные записи (client_id);
    - BARBER  → записи, где он мастер (barber_id);
    - MANAGER → все записи филиала, где он работает (по ManagerProfile);
    - ADMIN   → все записи всех филиалов.
    """
    q = (
        select(Appointment)
        .options(
            selectinload(Appointment.client),
            selectinload(Appointment.barber),
            selectinload(Appointment.branch),
            selectinload(Appointment.service),
        )
    )

    if current.role == UserRole.CLIENT:
        q = q.where(Appointment.client_id == current.id)
    elif current.role == UserRole.BARBER:
        q = q.where(Appointment.barber_id == current.id)
    elif current.role == UserRole.MANAGER:
        # Подтягиваем филиал менеджера (отдельным запросом — простая модель).
        from app.models import ManagerProfile  # локальный импорт чтобы не плодить циклы
        mp = (
            await db.execute(
                select(ManagerProfile).where(ManagerProfile.user_id == current.id)
            )
        ).scalar_one_or_none()
        if mp is None:
            return []
        q = q.where(Appointment.branch_id == mp.branch_id)
    # ADMIN — без фильтра, видит всё.

    rows = (await db.execute(q.order_by(Appointment.scheduled_at.desc()))).scalars().all()
    return [_to_detailed(a) for a in rows]


@router.get("/branch/{branch_id}", response_model=list[AppointmentDetailed])
async def list_branch_appointments(
    branch_id: str,
    current: User = Depends(require_roles(UserRole.MANAGER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[AppointmentDetailed]:
    """Менеджер/админ видят все записи филиала (F10)."""
    rows = (
        await db.execute(
            select(Appointment)
            .options(
                selectinload(Appointment.client),
                selectinload(Appointment.barber),
                selectinload(Appointment.branch),
                selectinload(Appointment.service),
            )
            .where(Appointment.branch_id == branch_id)
            .order_by(Appointment.scheduled_at)
        )
    ).scalars().all()
    return [_to_detailed(a) for a in rows]


# ---------- Смена статусов ----------


@router.put("/{appointment_id}/confirm", response_model=AppointmentPublic)
async def confirm_appointment(
    appointment_id: str,
    current: User = Depends(require_roles(UserRole.BARBER, UserRole.MANAGER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AppointmentPublic:
    apt = await _get_apt_or_404(db, appointment_id)
    if apt.status != AppointmentStatus.PENDING:
        raise HTTPException(status_code=400, detail="Можно подтвердить только ожидающую запись")
    if current.role == UserRole.BARBER and apt.barber_id != current.id:
        raise HTTPException(status_code=403, detail="Чужая запись")
    apt.status = AppointmentStatus.CONFIRMED
    await db.commit()
    await db.refresh(apt)
    return AppointmentPublic.model_validate(apt)


@router.put("/{appointment_id}/cancel", response_model=AppointmentPublic)
async def cancel_appointment(
    appointment_id: str,
    reason: str | None = Body(default=None, embed=True),
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppointmentPublic:
    """
    Отмена. Доступна клиенту (свою запись), менеджеру/админу (любую в филиале), барберу (свою).
    Шлёт email клиенту (F13).
    """
    apt = await _get_apt_or_404(db, appointment_id)
    if apt.status in (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Запись уже завершена или отменена")

    # RBAC.
    if current.role == UserRole.CLIENT and apt.client_id != current.id:
        raise HTTPException(status_code=403, detail="Чужая запись")
    if current.role == UserRole.BARBER and apt.barber_id != current.id:
        raise HTTPException(status_code=403, detail="Чужая запись")

    apt.status = AppointmentStatus.CANCELLED
    await db.commit()
    await db.refresh(apt)

    # F13: уведомление клиенту.
    client = (
        await db.execute(select(User).where(User.id == apt.client_id))
    ).scalar_one_or_none() if apt.client_id else None
    if client and client.is_active:
        asyncio.create_task(
            send_appointment_cancelled_email(
                to_email=client.email,
                client_name=client.full_name,
                scheduled_at=apt.scheduled_at,
                reason=reason,
            )
        )

    return AppointmentPublic.model_validate(apt)


@router.put("/{appointment_id}/complete", response_model=AppointmentPublic)
async def complete_appointment(
    appointment_id: str,
    current: User = Depends(require_roles(UserRole.BARBER, UserRole.MANAGER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AppointmentPublic:
    """F9: барбер фиксирует завершение услуги."""
    apt = await _get_apt_or_404(db, appointment_id)
    if current.role == UserRole.BARBER and apt.barber_id != current.id:
        raise HTTPException(status_code=403, detail="Чужая запись")
    if apt.status != AppointmentStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Завершить можно только подтверждённую или начатую запись")
    apt.status = AppointmentStatus.COMPLETED
    await db.commit()
    await db.refresh(apt)
    return AppointmentPublic.model_validate(apt)


# ---------- F11: заметка барбера ----------


@router.put("/{appointment_id}/barber-note", response_model=AppointmentPublic)
async def update_barber_note(
    appointment_id: str,
    payload: BarberNoteUpdate,
    current: User = Depends(require_roles(UserRole.BARBER)),
    db: AsyncSession = Depends(get_db),
) -> AppointmentPublic:
    apt = await _get_apt_or_404(db, appointment_id)
    if apt.barber_id != current.id:
        raise HTTPException(status_code=403, detail="Чужая запись")
    apt.barber_note = payload.barber_note
    await db.commit()
    await db.refresh(apt)
    return AppointmentPublic.model_validate(apt)


# ---------- helpers ----------


async def _get_apt_or_404(db: AsyncSession, apt_id: str) -> Appointment:
    apt = (await db.execute(select(Appointment).where(Appointment.id == apt_id))).scalar_one_or_none()
    if apt is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return apt


def _to_detailed(a: Appointment) -> AppointmentDetailed:
    return AppointmentDetailed(
        id=a.id,
        scheduled_at=a.scheduled_at,
        status=a.status,
        service_id=a.service_id,
        final_price=a.final_price,
        duration_minutes=a.duration_minutes,
        client_id=a.client_id,
        barber_id=a.barber_id,
        branch_id=a.branch_id,
        client_comment=a.client_comment,
        barber_note=a.barber_note,
        created_at=a.created_at,
        client_name=a.client.full_name if a.client else None,
        barber_name=a.barber.full_name if a.barber else None,
        branch_address=a.branch.address if a.branch else None,
        service_name=a.service.name if a.service else None,
    )
