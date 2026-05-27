"""Филиалы (F5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Branch
from app.schemas import BranchPublic

router = APIRouter()


@router.get("/", response_model=list[BranchPublic])
async def list_branches(db: AsyncSession = Depends(get_db)) -> list[Branch]:
    rows = (await db.execute(select(Branch).where(Branch.is_active == True))).scalars().all()  # noqa: E712
    return list(rows)


@router.get("/{branch_id}", response_model=BranchPublic)
async def get_branch(branch_id: str, db: AsyncSession = Depends(get_db)) -> Branch:
    branch = (await db.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if branch is None:
        raise HTTPException(status_code=404, detail="Филиал не найден")
    return branch
