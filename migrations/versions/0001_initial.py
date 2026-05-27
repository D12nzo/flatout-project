"""Initial schema (FlatOut v1).

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


# Используем postgresql.ENUM с create_type=False, чтобы SQLAlchemy НЕ пытался
# автоматически создать тип при первой ссылке на него в create_table().
# Сами типы создаём явным SQL один раз в начале upgrade() и удаляем в downgrade().

user_role_values = ("client", "barber", "manager", "admin")
barber_work_status_values = ("not_working", "working", "on_break", "fired")
appointment_status_values = (
    "pending", "confirmed", "completed", "cancelled",
)


def _enum_type(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # Идемпотентное создание ENUM-типов: если они остались от предыдущей неуспешной
    # попытки миграции — сначала удаляем, потом создаём заново.
    bind.exec_driver_sql("DROP TYPE IF EXISTS user_role CASCADE")
    bind.exec_driver_sql("DROP TYPE IF EXISTS barber_work_status CASCADE")
    bind.exec_driver_sql("DROP TYPE IF EXISTS appointment_status CASCADE")

    bind.exec_driver_sql(
        "CREATE TYPE user_role AS ENUM ('CLIENT', 'BARBER', 'MANAGER', 'ADMIN')"
    )
    bind.exec_driver_sql(
        "CREATE TYPE barber_work_status AS ENUM ('NOT_WORKING', 'WORKING', 'ON_BREAK', 'FIRED')"
    )
    bind.exec_driver_sql(
        "CREATE TYPE appointment_status AS ENUM "
        "('PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED')"
    )

    user_role = _enum_type("user_role", user_role_values)
    barber_work_status = _enum_type("barber_work_status", barber_work_status_values)
    appointment_status = _enum_type("appointment_status", appointment_status_values)

    # ---------- users ----------
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_visit", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])

    # ---------- branches ----------
    op.create_table(
        "branches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("opens_at", sa.Time, nullable=False),
        sa.Column("closes_at", sa.Time, nullable=False),
        sa.Column("work_stations", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    # ---------- services ----------
    op.create_table(
        "services",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("base_price", sa.Float, nullable=False),
        sa.Column("popularity", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    # ---------- barber_profiles ----------
    op.create_table(
        "barber_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  unique=True, nullable=False),
        sa.Column("branch_id", sa.String(36),
                  sa.ForeignKey("branches.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("specialization", sa.String(255), nullable=False, server_default=""),
        sa.Column("work_schedule", sa.String(255), nullable=False, server_default=""),
        sa.Column("salary", sa.Float, nullable=False, server_default="0"),
        sa.Column("rating", sa.Float, nullable=False, server_default="0"),
        sa.Column("price_multiplier", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("work_status", barber_work_status, nullable=False, server_default="NOT_WORKING"),
    )

    # ---------- manager_profiles ----------
    op.create_table(
        "manager_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  unique=True, nullable=False),
        sa.Column("branch_id", sa.String(36),
                  sa.ForeignKey("branches.id", ondelete="RESTRICT"),
                  nullable=False),
    )

    # ---------- appointments ----------
    op.create_table(
        "appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", appointment_status, nullable=False, server_default="PENDING"),
        sa.Column("service_id", sa.String(36),
                  sa.ForeignKey("services.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("final_price", sa.Float, nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("client_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("barber_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("branch_id", sa.String(36),
                  sa.ForeignKey("branches.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("client_comment", sa.String(1024), nullable=True),
        sa.Column("barber_note", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("barber_id", "scheduled_at", name="uq_barber_slot"),
    )
    op.create_index("ix_appointments_scheduled_at", "appointments", ["scheduled_at"])
    op.create_index("ix_appointments_branch_status", "appointments", ["branch_id", "status"])

    # ---------- audit_events ----------
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.String(2048), nullable=True),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_appointments_branch_status", table_name="appointments")
    op.drop_index("ix_appointments_scheduled_at", table_name="appointments")
    op.drop_table("appointments")

    op.drop_table("manager_profiles")
    op.drop_table("barber_profiles")
    op.drop_table("services")
    op.drop_table("branches")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    bind.exec_driver_sql("DROP TYPE IF EXISTS appointment_status")
    bind.exec_driver_sql("DROP TYPE IF EXISTS barber_work_status")
    bind.exec_driver_sql("DROP TYPE IF EXISTS user_role")
