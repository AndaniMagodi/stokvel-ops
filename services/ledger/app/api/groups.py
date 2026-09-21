"""Create and select stokvel groups by name."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.groups import StokvelGroup


router = APIRouter(tags=["groups"])


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class GroupResponse(BaseModel):
    id: UUID
    name: str
    created: bool


def _normalized_name(name: str) -> str:
    return " ".join(name.casefold().split())


@router.post("/groups", response_model=GroupResponse)
def create_group(request: GroupCreate, db: Session = Depends(get_db)) -> GroupResponse:
    name = " ".join(request.name.split())
    if not name:
        raise HTTPException(status_code=422, detail="Group name is required")
    normalized = _normalized_name(name)
    existing = db.scalar(
        select(StokvelGroup).where(StokvelGroup.normalized_name == normalized)
    )
    if existing:
        return GroupResponse(id=existing.id, name=existing.name, created=False)
    group = StokvelGroup(name=name, normalized_name=normalized)
    db.add(group)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(
            select(StokvelGroup).where(StokvelGroup.normalized_name == normalized)
        )
        if existing:
            return GroupResponse(id=existing.id, name=existing.name, created=False)
        raise HTTPException(status_code=409, detail="Group already exists") from exc
    return GroupResponse(id=group.id, name=group.name, created=True)


@router.get("/groups", response_model=list[GroupResponse])
def list_groups(db: Session = Depends(get_db)) -> list[GroupResponse]:
    return [
        GroupResponse(id=group.id, name=group.name, created=False)
        for group in db.scalars(select(StokvelGroup).order_by(StokvelGroup.name))
    ]


@router.get("/groups/{group_id}", response_model=GroupResponse)
def get_group(group_id: UUID, db: Session = Depends(get_db)) -> GroupResponse:
    group = db.get(StokvelGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return GroupResponse(id=group.id, name=group.name, created=False)
