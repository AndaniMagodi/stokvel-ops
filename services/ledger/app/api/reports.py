"""Treasurer reporting endpoints."""

from dataclasses import asdict
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.contributions.reporting import monthly_report
from app.db.session import get_db


router = APIRouter(tags=["reports"])


class MonthlyMemberResponse(BaseModel):
    member_id: UUID
    member_name: str
    status: str
    payment_received_cents: int
    contribution_cents: int
    fines_received_cents: int
    fine_due_cents: int
    fine_paid_cents: int


class MonthlyReportResponse(BaseModel):
    year: int
    month: int
    window_closed: bool
    payment_received_cents: int
    contribution_cents: int
    fines_received_cents: int
    members: list[MonthlyMemberResponse]


def _today() -> date:
    return datetime.now(ZoneInfo("Africa/Johannesburg")).date()


@router.get(
    "/groups/{group_id}/months/{year}/{month}",
    response_model=MonthlyReportResponse,
)
def get_monthly_report(
    group_id: UUID, year: int, month: int, db: Session = Depends(get_db),
) -> MonthlyReportResponse:
    try:
        report = monthly_report(db, group_id, year, month, as_of=_today())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MonthlyReportResponse(
        year=report.year,
        month=report.month,
        window_closed=report.window_closed,
        payment_received_cents=report.payment_received_cents,
        contribution_cents=report.contribution_cents,
        fines_received_cents=report.fines_received_cents,
        members=[asdict(item) for item in report.members],
    )
