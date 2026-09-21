"""Member registration and conservative reference matching."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.members import Member, MemberReference


def normalize_reference(reference: str) -> str:
    return "".join(char for char in reference.upper() if char.isalnum())


def normalize_sa_phone(number: str) -> str:
    digits = "".join(char for char in number if char.isdigit())
    if digits.startswith("27") and len(digits) == 11:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        digits = digits[1:]
    if len(digits) != 9:
        raise ValueError("Contact number must be a 9-digit SA number, optionally starting with 0 or +27")
    return digits


def register_member(
    db: Session, group_id: UUID, name: str, references: list[str],
    *, member_id: UUID | None = None,
    first_expected_year: int | None = None,
    first_expected_month: int | None = None,
    contact_number: str | None = None,
) -> Member:
    name = name.strip()
    if not name:
        raise ValueError("Member name is required")
    normalized = [normalize_reference(reference) for reference in references]
    if any(not value for value in normalized):
        raise ValueError("Payment references cannot be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate payment references")
    if (first_expected_year is None) != (first_expected_month is None):
        raise ValueError("First expected year and month must be supplied together")
    if first_expected_month is not None and not 1 <= first_expected_month <= 12:
        raise ValueError("First expected month must be between 1 and 12")
    if member_id is not None and db.get(Member, member_id) is not None:
        raise ValueError("Member ID already exists")
    details = dict(
        group_id=group_id, name=name,
        contact_number=normalize_sa_phone(contact_number) if contact_number else None,
        first_expected_year=first_expected_year,
        first_expected_month=first_expected_month,
    )
    member = Member(id=member_id, **details) if member_id else Member(**details)
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


def _inferred_reference_matches(
    db: Session, group_id: UUID, reference: str,
) -> list[Member]:
    target = normalize_reference(reference)
    matches = []
    for member in db.scalars(select(Member).where(Member.group_id == group_id)):
        parts = member.name.split()
        if len(parts) < 2:
            continue
        surname, given_name = parts[0], parts[-1]
        aliases = {
            normalize_reference(f"{given_name[0]} {surname}"),
            normalize_reference(f"{surname} {given_name[0]}"),
            normalize_reference(member.name),
            normalize_reference(" ".join(reversed(parts))),
        }
        if target in aliases:
            matches.append(member)
    return matches


def match_member(
    db: Session, group_id: UUID, *, reference: str | None, sender_phone: str | None,
) -> tuple[Member | None, str | None, bool]:
    """Return member, match method, and whether human resolution is required."""
    reference_matches: list[Member] = []
    if reference:
        explicit = find_member_by_reference(db, group_id, reference)
        reference_matches = [explicit] if explicit else _inferred_reference_matches(db, group_id, reference)
    phone_matches: list[Member] = []
    if sender_phone:
        normalized_phone = normalize_sa_phone(sender_phone)
        phone_matches = list(db.scalars(select(Member).where(
            Member.group_id == group_id, Member.contact_number == normalized_phone
        )))

    if reference_matches and phone_matches:
        intersection = [
            member for member in phone_matches
            if any(candidate.id == member.id for candidate in reference_matches)
        ]
        if len(intersection) == 1:
            return intersection[0], "phone_and_reference", False
        return None, None, True
    if len(phone_matches) == 1:
        return phone_matches[0], "phone", False
    if len(phone_matches) > 1:
        return None, None, True
    if len(reference_matches) == 1:
        return reference_matches[0], "reference", False
    if len(reference_matches) > 1:
        return None, None, True
    return None, None, False
