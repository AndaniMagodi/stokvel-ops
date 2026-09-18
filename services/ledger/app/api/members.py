"""Local treasurer member directory."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contributions.members import register_member
from app.db.session import get_db
from app.models.members import Member, MemberReference


router = APIRouter(tags=["members"])


class MemberCreate(BaseModel):
    group_id: UUID
    name: str = Field(min_length=1, max_length=200)
    references: list[str] = Field(min_length=1)
    member_id: UUID | None = None


class MemberResponse(BaseModel):
    id: UUID
    group_id: UUID
    name: str
    references: list[str]


@router.post("/members", response_model=MemberResponse, status_code=201)
def create_member(request: MemberCreate, db: Session = Depends(get_db)) -> MemberResponse:
    try:
        member = register_member(
            db, request.group_id, request.name, request.references,
            member_id=request.member_id,
        )
        response = MemberResponse(
            id=member.id, group_id=member.group_id,
            name=member.name, references=[value.strip() for value in request.references],
        )
        db.commit()
        return response
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Payment reference already belongs to a member") from exc


@router.get("/groups/{group_id}/members", response_model=list[MemberResponse])
def list_members(group_id: UUID, db: Session = Depends(get_db)) -> list[MemberResponse]:
    members = db.scalars(select(Member).where(Member.group_id == group_id).order_by(Member.name)).all()
    references = db.scalars(select(MemberReference).where(MemberReference.group_id == group_id)).all()
    by_member: dict[UUID, list[str]] = {}
    for reference in references:
        by_member.setdefault(reference.member_id, []).append(reference.reference)
    return [
        MemberResponse(
            id=member.id, group_id=group_id,
            name=member.name, references=by_member.get(member.id, []),
        )
        for member in members
    ]
