"""
Pydantic-схемы для валидации API.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import AppointmentStatus, BarberWorkStatus, UserRole


PhoneStr = Annotated[str, StringConstraints(min_length=5, max_length=32, strip_whitespace=True)]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]
PasswordStr = Annotated[str, StringConstraints(min_length=8, max_length=128)]


# ==================== AUTH ====================


class RegisterClientRequest(BaseModel):
    full_name: NonEmptyStr
    email: EmailStr
    phone: PhoneStr
    password: PasswordStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: UserRole
    full_name: str | None
    email: str | None


# ==================== USER ====================


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str | None
    email: str | None
    phone: str | None
    role: UserRole
    is_active: bool


# ==================== BRANCH ====================


class BranchPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    address: str
    phone: str
    opens_at: time
    closes_at: time
    work_stations: int
    is_active: bool


# ==================== SERVICE ====================


class ServicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    category: str
    duration_minutes: int
    base_price: float
    popularity: int
    is_active: bool


# ==================== BARBER ====================


class BarberPublic(BaseModel):
    """Барбер с раскрытыми полями профиля для UI."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    full_name: str | None
    branch_id: str
    specialization: str
    rating: float
    price_multiplier: float
    work_status: BarberWorkStatus


# ==================== APPOINTMENT ====================


class AppointmentCreateRequest(BaseModel):
    """
    client_id НЕ принимается от клиента — он подставляется из JWT.
    branch_id обязателен для проверки соответствия барбера филиалу (исправление "Барбер не найден").
    """
    branch_id: str
    barber_id: str
    service_id: str
    scheduled_at: datetime
    client_comment: str | None = Field(default=None, max_length=1024)


class AppointmentPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scheduled_at: datetime
    status: AppointmentStatus
    service_id: str
    final_price: float
    duration_minutes: int
    client_id: str | None
    barber_id: str
    branch_id: str
    client_comment: str | None
    barber_note: str | None
    created_at: datetime


class AppointmentDetailed(AppointmentPublic):
    client_name: str | None = None
    barber_name: str | None = None
    branch_address: str | None = None
    service_name: str | None = None


class BarberNoteUpdate(BaseModel):
    """F11: барбер оставляет/обновляет заметку о клиенте на конкретной записи."""
    barber_note: str = Field(..., max_length=1024)


# ==================== AVAILABLE SLOTS ====================


class SlotsQuery(BaseModel):
    branch_id: str
    service_id: str
    barber_id: str | None = None  # None = любой свободный барбер филиала
    target_date: date


class SlotPublic(BaseModel):
    barber_id: str
    barber_name: str | None
    start: datetime
    duration_minutes: int


class SlotsResponse(BaseModel):
    target_date: date
    branch_id: str
    service_id: str
    slots: list[SlotPublic]


# ==================== REPORTS (F12) ====================


class RevenueByBarberRow(BaseModel):
    barber_id: str
    barber_name: str | None
    appointments_count: int
    total_revenue: float


class PopularServiceRow(BaseModel):
    service_id: str
    service_name: str
    appointments_count: int
    total_revenue: float


class BranchReport(BaseModel):
    branch_id: str
    period_start: date
    period_end: date
    total_appointments: int
    completed_appointments: int
    total_revenue: float
    by_barber: list[RevenueByBarberRow]
    top_services: list[PopularServiceRow]
