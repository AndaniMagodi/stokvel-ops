"""Member registration and conservative reference matching."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.members import Member, MemberReference


def normalize_reference(reference: str) -> str:
    return "".join(char for char in reference.upper() if char.isalnum())


def register_member(
    db: Session, group_id: UUID, name: str, references: list[str],
    *, member_id: UUID | None = None,
) -> Member:
    name = name.strip()
    if not name:
        raise ValueError("Member name is required")
    normalized = [normalize_reference(reference) for reference in references]
    if not references or any(not value for value in normalized):
        raise ValueError("At least one nonempty payment reference is required")
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate payment references")
    if member_id is not None and db.get(Member, member_id) is not None:
        raise ValueError("Member ID already exists")
    member = Member(id=member_id, group_id=group_id, name=name) if member_id else Member(group_id=group_id, name=name)
    db.add(member)
    db.flush()
    for reference, value in zip(references, normalized, strict=True):
        db.add(MemberReference(
            group_id=group_id, member_id=member.id,
            reference=reference.strip(), normalized_reference=value,
        ))
    db.flush()
    return member


def find_member_by_reference(db: Session, group_id: UUID, reference: str) -> Member | None:
    normalized = normalize_reference(reference)
    if not normalized:
        return None
    return db.scalar(
        select(Member)
        .join(MemberReference, MemberReference.member_id == Member.id)
        .where(
            Member.group_id == group_id,
            MemberReference.group_id == group_id,
            MemberReference.normalized_reference == normalized,
        )
    )
