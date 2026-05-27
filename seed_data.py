"""
Наполнение БД демо-данными FlatOut.

Запуск:  python seed_data.py
Требует: применённых миграций Alembic.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import text

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import (
    Appointment,
    AppointmentStatus,
    BarberProfile,
    BarberWorkStatus,
    Branch,
    ManagerProfile,
    Service,
    User,
    UserRole,
)


# Порядок удаления учитывает FK.
TABLES_TO_TRUNCATE = (
    "appointments",
    "audit_events",
    "barber_profiles",
    "manager_profiles",
    "users",
    "branches",
    "services",
)


async def clear_database() -> None:
    async with AsyncSessionLocal() as session:
        for t in TABLES_TO_TRUNCATE:
            await session.execute(text(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE"))
        await session.commit()
    print("🗑️  База очищена")


# ---------- Контент ----------


BRANCHES = [
    # ТЗ: все филиалы сети работают с 09:00 до 21:00.
    Branch(id="branch-lenina",  address="ул. Ленина, 25",       phone="+73952123456",
           opens_at=time(9, 0), closes_at=time(21, 0), work_stations=5, is_active=True),
    Branch(id="branch-marksa",  address="ул. Карла Маркса, 48", phone="+73952234567",
           opens_at=time(9, 0), closes_at=time(21, 0), work_stations=5, is_active=True),
    Branch(id="branch-telmana", address="ул. Тельмана, 12",     phone="+73952345678",
           opens_at=time(9, 0), closes_at=time(21, 0), work_stations=5, is_active=True),
]


def _mk_user(role: UserRole, full_name: str, email: str, phone: str, password: str) -> User:
    return User(
        id=str(uuid.uuid4()),
        full_name=full_name,
        email=email,
        phone=phone,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )


# (имя, email-локальная часть, телефон, рейтинг, multiplier).
# Специализация у всех одинакова — все мастера универсалы; визуально отличаются
# только рейтингом и индивидуальным ценовым коэффициентом (price_multiplier).
BARBERS_BY_BRANCH: dict[str, list[tuple[str, str, str, float, float]]] = {
    "branch-lenina": [
        ("Сергей Мартынов",   "sergey.lenina",   "+79150991960", 4.9, 1.10),
        ("Дмитрий Матюшин",   "dmitry.lenina",   "+79025551844", 4.8, 1.05),
        ("Максим Соколов",    "maxim.lenina",    "+79025551845", 4.7, 1.00),
        ("Андрей Волков",     "andrey.lenina",   "+79025551846", 4.6, 1.00),
        ("Олег Кузнецов",     "oleg.lenina",     "+79025551847", 4.9, 1.10),
    ],
    "branch-marksa": [
        ("Владислав Егоров",  "vlad.marksa",     "+79025551848", 5.0, 1.15),
        ("Александр Новиков", "alex.marksa",     "+79025551849", 4.7, 1.05),
        ("Игорь Петров",      "igor.marksa",     "+79025551850", 4.9, 1.10),
        ("Николай Морозов",   "nikolay.marksa",  "+79025551851", 4.6, 1.00),
        ("Евгений Смирнов",   "evgeny.marksa",   "+79025551852", 4.8, 1.05),
    ],
    "branch-telmana": [
        ("Виктор Васильев",   "viktor.telmana",  "+79025551853", 4.8, 1.05),
        ("Артем Лебедев",     "artem.telmana",   "+79025551854", 4.7, 1.00),
        ("Денис Федоров",     "denis.telmana",   "+79025551855", 4.9, 1.10),
        ("Роман Захаров",     "roman.telmana",   "+79025551856", 4.6, 1.00),
        ("Станислав Орлов",   "stanislav.telmana","+79025551857", 4.8, 1.05),
    ],
}

#: Единая специализация — все мастера универсалы.
UNIVERSAL_SPECIALIZATION = "Универсал (все виды услуг)"


SERVICES = [
    Service(id="svc-haircut-classic",  name="Мужская стрижка",                category="Стрижки",      duration_minutes=40, base_price=1500, popularity=150, is_active=True),
    Service(id="svc-haircut-machine",  name="Мужская стрижка машинкой",       category="Стрижки",      duration_minutes=20, base_price=500,  popularity=80,  is_active=True),
    Service(id="svc-haircut-kids",     name="Детская стрижка (до 12 лет)",    category="Стрижки",      duration_minutes=30, base_price=1000, popularity=60,  is_active=True),
    Service(id="svc-haircut-model",    name="Модельная стрижка",              category="Стрижки",      duration_minutes=60, base_price=2000, popularity=70,  is_active=True),
    Service(id="svc-haircut-styling",  name="Стрижка + укладка",              category="Стрижки",      duration_minutes=50, base_price=1800, popularity=50,  is_active=True),
    Service(id="svc-royal-shave",      name="Королевское бритьё",             category="Бритьё",       duration_minutes=90, base_price=2500, popularity=40,  is_active=True),
    Service(id="svc-beard-trim",       name="Коррекция бороды",               category="Бритьё",       duration_minutes=30, base_price=800,  popularity=100, is_active=True),
    Service(id="svc-beard-shape",      name="Оформление бороды и усов",       category="Бритьё",       duration_minutes=40, base_price=1200, popularity=65,  is_active=True),
    Service(id="svc-head-shave",       name="Бритьё головы",                  category="Бритьё",       duration_minutes=30, base_price=900,  popularity=30,  is_active=True),
    Service(id="svc-styling",          name="Укладка волос",                  category="Укладка",      duration_minutes=20, base_price=600,  popularity=45,  is_active=True),
    Service(id="svc-color-hair",       name="Окрашивание волос",              category="Окрашивание",  duration_minutes=60, base_price=2000, popularity=30,  is_active=True),
    Service(id="svc-color-beard",      name="Окрашивание бороды",             category="Окрашивание",  duration_minutes=40, base_price=1200, popularity=25,  is_active=True),
    Service(id="svc-camouflage",       name="Камуфляж седины",                category="Окрашивание",  duration_minutes=30, base_price=1500, popularity=40,  is_active=True),
    Service(id="svc-vip-combo",        name="VIP комплекс (стрижка+бритьё+укладка)", category="Комплексы", duration_minutes=120, base_price=4000, popularity=35, is_active=True),
    Service(id="svc-std-combo",        name="Стандарт (стрижка + борода)",    category="Комплексы",    duration_minutes=70, base_price=2200, popularity=55,  is_active=True),
]


async def seed_database() -> None:
    async with AsyncSessionLocal() as session:
        # Филиалы.
        session.add_all(BRANCHES)
        await session.flush()

        # Админ.
        admin = _mk_user(UserRole.ADMIN, "Симонов Данил", "admin@flatout.ru", "+79135981451", "admin123")
        session.add(admin)

        # Менеджеры — по одному на филиал.
        managers_meta = [
            ("Попова Анна",        "manager.lenina@flatout.ru",  "+79131789721", "branch-lenina"),
            ("Дорошенко Кристина", "manager.marksa@flatout.ru",  "+79131789722", "branch-marksa"),
            ("Аракелян Лилит",     "manager.telmana@flatout.ru", "+79131789723", "branch-telmana"),
        ]
        managers: list[tuple[User, str]] = []
        for name, email, phone, branch_id in managers_meta:
            u = _mk_user(UserRole.MANAGER, name, email, phone, "manager123")
            session.add(u)
            managers.append((u, branch_id))

        # Барберы — по 5 на филиал.
        barbers: list[tuple[User, str, float, float]] = []
        for branch_id, items in BARBERS_BY_BRANCH.items():
            for name, local, phone, rating, mult in items:
                u = _mk_user(UserRole.BARBER, name, f"{local}@flatout.ru", phone, "barber123")
                session.add(u)
                barbers.append((u, branch_id, rating, mult))

        # Клиенты.
        clients_meta = [
            ("Иван Петров",       "ivan@mail.ru",       "+79161234567", 120),
            ("Алексей Смирнов",   "alex@mail.ru",       "+79161234568",  90),
            ("Павел Морозов",     "pavel@mail.ru",      "+79161234569",  60),
            ("Сергей Федотов",    "sergey.f@mail.ru",   "+79161234570",  45),
            ("Дмитрий Козлов",    "dmitry.k@mail.ru",   "+79161234571",  30),
            ("Андрей Волков-кл",  "andrey@mail.ru",     "+79161234572",  15),
            ("Михаил Иванов",     "misha@mail.ru",      "+79161234573",  80),
            ("Артём Соловьёв",    "artem.s@mail.ru",    "+79161234574",  70),
            ("Кирилл Лазарев",    "kirill@mail.ru",     "+79161234575",  55),
            ("Антон Громов",      "anton@mail.ru",      "+79161234576",  40),
            ("Никита Белов",      "nikita@mail.ru",     "+79161234577",  25),
            ("Глеб Тимофеев",     "gleb@mail.ru",       "+79161234578",  10),
        ]
        clients: list[User] = []
        now = datetime.now(timezone.utc)
        for name, email, phone, days_ago in clients_meta:
            c = _mk_user(UserRole.CLIENT, name, email, phone, "client123")
            c.created_at = now - timedelta(days=days_ago)
            session.add(c)
            clients.append(c)

        # Услуги.
        session.add_all(SERVICES)
        await session.flush()  # получаем все ID.

        # Профили менеджеров и барберов.
        for user, branch_id in managers:
            session.add(ManagerProfile(user_id=user.id, branch_id=branch_id))

        barber_users_for_apts: list[tuple[User, str]] = []
        for user, branch_id, rating, mult in barbers:
            session.add(
                BarberProfile(
                    user_id=user.id,
                    branch_id=branch_id,
                    specialization=UNIVERSAL_SPECIALIZATION,
                    work_schedule="Пн-Пт 9:00-21:00",
                    salary=50_000.0,
                    rating=rating,
                    price_multiplier=mult,
                    work_status=BarberWorkStatus.NOT_WORKING,
                )
            )
            barber_users_for_apts.append((user, branch_id))

        await session.flush()

        # ---------- Демо-записи ----------
        #
        # Генерим ~150 записей за последние 60 дней + на 14 дней вперёд.
        # Распределение статусов:
        #   - 90% прошедших → COMPLETED
        #   - 10% прошедших → CANCELLED (отказались)
        #   - будущие: 60% CONFIRMED, 40% PENDING
        #
        # Уникальность (barber_id, scheduled_at) гарантируется множеством used_slots,
        # поэтому повторных пар не будет — UniqueConstraint не сработает.

        import random
        random.seed(42)  # детерминированность — каждый запуск получает одинаковые данные.

        # Индекс multiplier по user_id, чтобы быстро считать final_price.
        mult_by_user_id = {u.id: m for u, _, _, m in barbers}

        # Список (барбер, филиал) для удобного выбора.
        barber_branch_pairs = [(u, br) for u, br, _, _ in barbers]

        used_slots: set[tuple[str, datetime]] = set()
        all_apts: list[Appointment] = []
        now_dt = datetime.now(timezone.utc)

        # Часы, в которые обычно бывают записи (рабочее время филиала 9-21).
        work_hours = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
        work_minutes = [0, 30]

        def _try_make_apt(target_dt: datetime, is_future: bool) -> bool:
            """Создаёт запись на target_dt со случайным барбером/клиентом/услугой.
            Возвращает True если запись создана, False если слот занят (нужно пропустить).
            """
            barber_user, branch_id = random.choice(barber_branch_pairs)
            key = (barber_user.id, target_dt)
            if key in used_slots:
                return False
            used_slots.add(key)

            client = random.choice(clients)
            service = random.choice(SERVICES)

            # Статус зависит от того, в прошлом ли запись.
            if is_future:
                status = random.choices(
                    [AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING],
                    weights=[60, 40],
                )[0]
            else:
                status = random.choices(
                    [
                        AppointmentStatus.COMPLETED,
                        AppointmentStatus.CANCELLED,
                    ],
                    weights=[90, 10],
                )[0]

            mult = mult_by_user_id[barber_user.id]
            all_apts.append(
                Appointment(
                    id=str(uuid.uuid4()),
                    scheduled_at=target_dt,
                    status=status,
                    service_id=service.id,
                    final_price=round(service.base_price * mult, 2),
                    duration_minutes=service.duration_minutes,
                    client_id=client.id,
                    barber_id=barber_user.id,
                    branch_id=branch_id,
                    client_comment=None,
                )
            )
            return True

        # Прошлые 60 дней — по 2-3 записи в день.
        for days_back in range(1, 61):
            day = (now_dt - timedelta(days=days_back)).replace(microsecond=0, second=0)
            attempts = 0
            created = 0
            target = random.randint(2, 4)
            while created < target and attempts < 30:
                hour = random.choice(work_hours)
                minute = random.choice(work_minutes)
                dt = day.replace(hour=hour, minute=minute)
                if _try_make_apt(dt, is_future=False):
                    created += 1
                attempts += 1

        # Ближайшие 14 дней — по 1-2 записи на день.
        for days_fwd in range(1, 15):
            day = (now_dt + timedelta(days=days_fwd)).replace(microsecond=0, second=0)
            attempts = 0
            created = 0
            target = random.randint(1, 3)
            while created < target and attempts < 30:
                hour = random.choice(work_hours)
                minute = random.choice(work_minutes)
                dt = day.replace(hour=hour, minute=minute)
                if _try_make_apt(dt, is_future=True):
                    created += 1
                attempts += 1

        session.add_all(all_apts)
        await session.commit()

        print("✅ Данные загружены")
        print(f"   📍 Филиалов: {len(BRANCHES)}  (все: 09:00–21:00)")
        print(f"   👨‍🦰 Барберов: {sum(len(v) for v in BARBERS_BY_BRANCH.values())} (по 5 на филиал)")
        print(f"   👤 Клиентов: {len(clients)}")
        print(f"   ✂️  Услуг: {len(SERVICES)}")
        print(f"   📋 Записей: {len(all_apts)}")


async def main() -> None:
    print("🧹 Очистка БД...")
    await clear_database()
    print("📦 Заполнение демо-данными...")
    await seed_database()
    print()
    print("=" * 50)
    print("Тестовые учётки (пароли в plaintext — только для dev):")
    print("  👤 Клиент:   ivan@mail.ru / client123")
    print("  👨‍🦰 Барбер:   sergey.lenina@flatout.ru / barber123")
    print("  👔 Менеджер: manager.lenina@flatout.ru / manager123")
    print("  🛡️  Админ:    admin@flatout.ru / admin123")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
