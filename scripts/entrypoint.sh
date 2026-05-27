#!/bin/sh
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Checking if seed is needed..."
NEED_SEED=$(python -c "
import asyncio
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models import Branch

async def check():
    async with AsyncSessionLocal() as s:
        count = (await s.execute(select(func.count(Branch.id)))).scalar_one()
        print('yes' if count == 0 else 'no')

asyncio.run(check())
")

if [ "$NEED_SEED" = "yes" ]; then
    echo "==> Database is empty — seeding demo data..."
    python seed_data.py
else
    echo "==> Database already has data — skipping seed."
fi

echo "==> Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
