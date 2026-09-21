"""Local treasurer member directory."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contributions.member_import import ImportError as MemberImportError, import_members
from app.contributions.members import register_member
from app.db.session import get_db
from app.models.members import Member, MemberReference


router = APIRouter(tags=["members"])


class MemberCreate(BaseModel):
    group_id: UUID
    name: str = Field(min_length=1, max_length=200)
    references: list[str] = Field(default_factory=list)
    member_id: UUID | None = None
    first_expected_year: int | None = None
    first_expected_month: int | None = Field(default=None, ge=1, le=12)
    contact_number: str | None = Field(default=None, max_length=30)


class MemberResponse(BaseModel):
    id: UUID
    group_id: UUID
    name: str
    references: list[str]
    first_expected_year: int | None
    first_expected_month: int | None
    contact_number: str | None


class FirstExpectedMonthRequest(BaseModel):
    year: int
    month: int = Field(ge=1, le=12)


class ContactNumberRequest(BaseModel):
    contact_number: str = Field(min_length=1, max_length=30)


class MemberImportResponse(BaseModel):
    created: int
    skipped_existing: int
    missing_contact_numbers: int
    shared_contact_numbers: int
    warnings: list[str]


@router.post("/groups/{group_id}/members/import", response_model=MemberImportResponse)
async def import_member_spreadsheet(
    group_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
) -> MemberImportResponse:
    data = await file.read(3 * 1024 * 1024 + 1)
    try:
        result = import_members(db, group_id, data)
        db.commit()
        return MemberImportResponse(**result)
    except MemberImportError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Spreadsheet conflicts with existing member data") from exc


@router.post("/members", response_model=MemberResponse, status_code=201)
def create_member(request: MemberCreate, db: Session = Depends(get_db)) -> MemberResponse:
    try:
        member = register_member(
            db, request.group_id, request.name, request.references,
            member_id=request.member_id,
            first_expected_year=request.first_expected_year,
            first_expected_month=request.first_expected_month,
            contact_number=request.contact_number,
        )
        response = MemberResponse(
            id=member.id, group_id=member.group_id,
            name=member.name, references=[value.strip() for value in request.references],
            first_expected_year=member.first_expected_year,
            first_expected_month=member.first_expected_month,
            contact_number=member.contact_number,
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
            first_expected_year=member.first_expected_year,
            first_expected_month=member.first_expected_month,
            contact_number=member.contact_number,
        )
        for member in members
    ]


@router.patch(
    "/groups/{group_id}/members/{member_id}/first-expected-month",
    response_model=MemberResponse,
)
def set_first_expected_month(
    group_id: UUID, member_id: UUID, request: FirstExpectedMonthRequest,
    db: Session = Depends(get_db),
) -> MemberResponse:
    member = db.scalar(select(Member).where(Member.group_id == group_id, Member.id == member_id))
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found in group")
    member.first_expected_year = request.year
    member.first_expected_month = request.month
    references = db.scalars(
        select(MemberReference.reference).where(MemberReference.member_id == member_id)
    ).all()
    db.commit()
    return MemberResponse(
        id=member.id, group_id=group_id, name=member.name, references=list(references),
        first_expected_year=member.first_expected_year,
        first_expected_month=member.first_expected_month,
        contact_number=member.contact_number,
    )


@router.patch(
    "/groups/{group_id}/members/{member_id}/contact-number",
    response_model=MemberResponse,
)
def set_contact_number(
    group_id: UUID, member_id: UUID, request: ContactNumberRequest,
    db: Session = Depends(get_db),
) -> MemberResponse:
    from app.contributions.members import normalize_sa_phone

    member = db.scalar(select(Member).where(Member.group_id == group_id, Member.id == member_id))
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found in group")
    try:
        member.contact_number = normalize_sa_phone(request.contact_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    references = db.scalars(
        select(MemberReference.reference).where(MemberReference.member_id == member_id)
    ).all()
    db.commit()
    return MemberResponse(
        id=member.id, group_id=group_id, name=member.name, references=list(references),
        first_expected_year=member.first_expected_year,
        first_expected_month=member.first_expected_month,
        contact_number=member.contact_number,
    )
