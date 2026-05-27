"""
ORM-модели FlatOut.

Дизайн:
  * Единая таблица users с полем role (Enum: client/barber/manager/admin) — F2.
  * Профильные таблицы (BarberProfile, ManagerProfile) — для специфичных полей
    барбера/менеджера, связанных с филиалом (1:1 к User).
  * Мягкое удаление через User.is_active (152-ФЗ): персональные данные затираются,
    запись пользователя остаётся, ссылочная целостность с appointments не нарушается.
  * Appointment хранит final_price (для F12 аналитики) и ссылается на Service через FK.
  * UniqueConstraint(barber_id, scheduled_at) — страховка от race condition на уровне БД (F7).
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ==================== ENUMS ====================


class UserRole(str, PyEnum):
    """Четыре роли пользователей (F2)."""
    CLIENT = "CLIENT"
    BARBER = "BARBER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"


class BarberWorkStatus(str, PyEnum):
    """Состояние барбера из диаграммы состояний (раздел 13.4 ТЗ)."""
    NOT_WORKING = "NOT_WORKING"
    WORKING = "WORKING"
    ON_BREAK = "ON_BREAK"
    FIRED = "FIRED"


class AppointmentStatus(str, PyEnum):
    """Состояние записи. Жизненный цикл: PENDING → CONFIRMED → COMPLETED,
    с возможностью перехода в CANCELLED с любого активного статуса."""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


#: Статусы, при которых слот считается занятым (для проверок F7).
ACTIVE_STATUSES: tuple[AppointmentStatus, ...] = (
    AppointmentStatus.PENDING,
    AppointmentStatus.CONFIRMED,
)


# ==================== USER ====================


class User(Base):
    """
    Единый пользователь системы. Роль (role) определяет доступ к API.
    Профильные таблицы (BarberProfile, ManagerProfile) хранят роль-специфичные поля.
    """
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_role", "role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # ВАЖНО для 152-ФЗ: после мягкого удаления имя/email/phone затираются,
    # поэтому все nullable=True. До удаления они валидируются на уровне Pydantic.
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    last_visit: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Профили (1:1) — заполнены только для соответствующих ролей.
    barber_profile: Mapped["BarberProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    manager_profile: Mapped["ManagerProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    # Записи клиента — НЕ каскадно удаляются (F12: аналитика по final_price должна сохраниться).
    client_appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="client",
        foreign_keys="Appointment.client_id",
        passive_deletes=True,
    )

    # Записи, обслуживаемые барбером.
    barber_appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="barber",
        foreign_keys="Appointment.barber_id",
        passive_deletes=True,
    )


# ==================== BRANCH ====================


class Branch(Base):
    """
    Филиал. opens_at/closes_at хранятся как Time — для алгоритмической генерации слотов.
    """
    __tablename__ = "branches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    opens_at: Mapped[time] = mapped_column(Time, nullable=False)
    closes_at: Mapped[time] = mapped_column(Time, nullable=False)
    work_stations: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    barbers: Mapped[list["BarberProfile"]] = relationship(back_populates="branch")
    managers: Mapped[list["ManagerProfile"]] = relationship(back_populates="branch")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="branch")


# ==================== BARBER / MANAGER PROFILES ====================


class BarberProfile(Base):
    """Специфика барбера (F4). Связь 1:1 с User (user_id уникален)."""
    __tablename__ = "barber_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    branch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )

    specialization: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    work_schedule: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    salary: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Индивидуальный ценовой коэффициент (ТЗ: «финальная цена зависит от категории мастера»).
    price_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    work_status: Mapped[BarberWorkStatus] = mapped_column(
        Enum(
            BarberWorkStatus,
            name="barber_work_status",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=BarberWorkStatus.NOT_WORKING,
    )

    user: Mapped[User] = relationship(back_populates="barber_profile")
    branch: Mapped[Branch] = relationship(back_populates="barbers")


class ManagerProfile(Base):
    """Специфика менеджера филиала."""
    __tablename__ = "manager_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    branch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="manager_profile")
    branch: Mapped[Branch] = relationship(back_populates="managers")


# ==================== SERVICE ====================


class Service(Base):
    """Справочник услуг (F3). Базовая цена — единая по сети, финальная цена считается на записи."""
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    base_price: Mapped[float] = mapped_column(Float, nullable=False)
    popularity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ==================== APPOINTMENT ====================


class Appointment(Base):
    """
    Запись клиента на услугу.

    F7 (атомарность): UniqueConstraint(barber_id, scheduled_at) гарантирует, что СУБД
    физически не примет два конкурентных INSERT на один и тот же слот — даже если
    пессимистическая блокировка не сработала (страховочный слой).

    F12 (аналитика): final_price фиксируется в момент создания записи как
    service.base_price * barber.price_multiplier и НЕ меняется, даже если базовый прайс позже
    скорректируют. Это даёт корректную историческую выручку для отчётов.

    Мягкое удаление клиента: client_id остаётся, ondelete='SET NULL' — на случай
    физического удаления (для тестов). По бизнес-правилу клиент удаляется мягко (is_active=False).
    """
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("barber_id", "scheduled_at", name="uq_barber_slot"),
        Index("ix_appointments_scheduled_at", "scheduled_at"),
        Index("ix_appointments_branch_status", "branch_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Единое поле даты-времени слота — упрощает выборки и уникальный индекс.
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            name="appointment_status",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AppointmentStatus.PENDING,
    )

    # FK на сервис — для фильтрации барберов по услуге и расчёта final_price.
    service_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("services.id", ondelete="RESTRICT"), nullable=False
    )

    # Зафиксированные на момент записи параметры (для аналитики и истории).
    final_price: Mapped[float] = mapped_column(Float, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    client_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    barber_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    branch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False
    )

    client_comment: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    barber_note: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # F11

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    client: Mapped[User | None] = relationship(
        back_populates="client_appointments", foreign_keys=[client_id]
    )
    barber: Mapped[User] = relationship(
        back_populates="barber_appointments", foreign_keys=[barber_id]
    )
    branch: Mapped[Branch] = relationship(back_populates="appointments")
    service: Mapped[Service] = relationship()


# ==================== AUDIT LOG (F14) ====================


class AuditEvent(Base):
    """Журнал событий (F14). Хранится не менее года; срок хранения — на стороне политик retention."""
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[str | None] = mapped_column(String(2048), nullable=True)
