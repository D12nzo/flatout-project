"""
Отчёты (F12). Используют final_price из таблицы appointments —
поэтому мягкое удаление клиентов не влияет на корректность аналитики.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.database import get_db
from app.models import (
    Appointment,
    AppointmentStatus,
    ManagerProfile,
    Service,
    User,
    UserRole,
)
from app.schemas import (
    BranchReport,
    PopularServiceRow,
    RevenueByBarberRow,
)

router = APIRouter()


@router.get("/branch/{branch_id}", response_model=BranchReport)
async def branch_report(
    branch_id: str,
    period_start: date = Query(...),
    period_end: date = Query(...),
    current: User = Depends(require_roles(UserRole.MANAGER, UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> BranchReport:
    """
    Отчёт по филиалу за период. Менеджер видит только свой филиал, админ — любой.
    """
    if period_end < period_start:
        raise HTTPException(status_code=400, detail="period_end раньше period_start")

    # RBAC: менеджер вне своего филиала запрос делать не может.
    if current.role == UserRole.MANAGER:
        mp = (
            await db.execute(select(ManagerProfile).where(ManagerProfile.user_id == current.id))
        ).scalar_one_or_none()
        if mp is None or mp.branch_id != branch_id:
            raise HTTPException(status_code=403, detail="Доступ только к своему филиалу")

    start_dt = datetime.combine(period_start, time(0, 0))
    end_dt = datetime.combine(period_end + timedelta(days=1), time(0, 0))

    base_where = (
        Appointment.branch_id == branch_id,
        Appointment.scheduled_at >= start_dt,
        Appointment.scheduled_at < end_dt,
    )

    total = (
        await db.execute(select(func.count(Appointment.id)).where(*base_where))
    ).scalar_one()

    completed_where = base_where + (Appointment.status == AppointmentStatus.COMPLETED,)

    completed = (
        await db.execute(select(func.count(Appointment.id)).where(*completed_where))
    ).scalar_one()

    revenue = (
        await db.execute(select(func.coalesce(func.sum(Appointment.final_price), 0.0)).where(*completed_where))
    ).scalar_one()

    # Выручка по барберам.
    by_barber_rows = (
        await db.execute(
            select(
                Appointment.barber_id,
                User.full_name,
                func.count(Appointment.id),
                func.coalesce(func.sum(Appointment.final_price), 0.0),
            )
            .join(User, User.id == Appointment.barber_id)
            .where(*completed_where)
            .group_by(Appointment.barber_id, User.full_name)
            .order_by(func.sum(Appointment.final_price).desc())
        )
    ).all()
    by_barber = [
        RevenueByBarberRow(
            barber_id=row[0],
            barber_name=row[1],
            appointments_count=row[2],
            total_revenue=float(row[3] or 0.0),
        )
        for row in by_barber_rows
    ]

    # Топ услуг.
    top_rows = (
        await db.execute(
            select(
                Appointment.service_id,
                Service.name,
                func.count(Appointment.id),
                func.coalesce(func.sum(Appointment.final_price), 0.0),
            )
            .join(Service, Service.id == Appointment.service_id)
            .where(*completed_where)
            .group_by(Appointment.service_id, Service.name)
            .order_by(func.count(Appointment.id).desc())
            .limit(10)
        )
    ).all()
    top_services = [
        PopularServiceRow(
            service_id=row[0],
            service_name=row[1],
            appointments_count=row[2],
            total_revenue=float(row[3] or 0.0),
        )
        for row in top_rows
    ]

    return BranchReport(
        branch_id=branch_id,
        period_start=period_start,
        period_end=period_end,
        total_appointments=total,
        completed_appointments=completed,
        total_revenue=float(revenue or 0.0),
        by_barber=by_barber,
        top_services=top_services,
    )
