"""
Email-уведомления (F13).

SMS из системы полностью исключён по требованию ТЗ.
Текущая реализация — асинхронные заглушки, пишущие сообщение в stdout.
Интерфейс готов к замене на реальный SMTP / провайдер (SendGrid, Mailgun)
без изменений в вызывающем коде.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger("flatout.notifications")


async def _deliver(to_email: str, subject: str, body: str) -> None:
    """Внутренняя точка доставки. В тестах подменяется monkeypatch'ем."""
    # Имитация сетевой задержки внешнего почтового провайдера.
    await asyncio.sleep(0)
    logger.info("EMAIL → %s | %s\n%s", to_email, subject, body)


async def send_appointment_confirmation_email(
    to_email: str | None,
    client_name: str | None,
    scheduled_at: datetime,
    service_name: str,
    branch_address: str,
    barber_name: str | None,
    final_price: float,
) -> None:
    """Отправляется сразу после успешного создания записи."""
    if not to_email:
        return  # У мягко удалённого клиента email затёрт — пропускаем.
    subject = "FlatOut — ваша запись подтверждена"
    body = (
        f"Здравствуйте, {client_name or 'клиент'}!\n\n"
        f"Вы записаны на услугу «{service_name}»\n"
        f"Барбер: {barber_name or 'будет назначен'}\n"
        f"Дата и время: {scheduled_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"Адрес: {branch_address}\n"
        f"Стоимость: {final_price:.2f} ₽\n\n"
        f"Если планы изменятся — отмените или перенесите визит в личном кабинете."
    )
    await _deliver(to_email, subject, body)


async def send_appointment_reminder_email(
    to_email: str | None,
    client_name: str | None,
    scheduled_at: datetime,
    service_name: str,
    branch_address: str,
) -> None:
    """Напоминание о визите (за N часов до slot)."""
    if not to_email:
        return
    subject = "FlatOut — напоминание о визите"
    body = (
        f"Здравствуйте, {client_name or 'клиент'}!\n\n"
        f"Напоминаем: {scheduled_at.strftime('%d.%m.%Y в %H:%M')} вас ждут "
        f"на услугу «{service_name}» по адресу {branch_address}."
    )
    await _deliver(to_email, subject, body)


async def send_appointment_cancelled_email(
    to_email: str | None,
    client_name: str | None,
    scheduled_at: datetime,
    reason: str | None,
) -> None:
    """Уведомление об отмене (по инициативе клиента или менеджера)."""
    if not to_email:
        return
    subject = "FlatOut — запись отменена"
    body = (
        f"Здравствуйте, {client_name or 'клиент'}!\n\n"
        f"Ваша запись на {scheduled_at.strftime('%d.%m.%Y в %H:%M')} отменена.\n"
        + (f"Причина: {reason}\n" if reason else "")
    )
    await _deliver(to_email, subject, body)


__all__ = [
    "send_appointment_confirmation_email",
    "send_appointment_reminder_email",
    "send_appointment_cancelled_email",
]
