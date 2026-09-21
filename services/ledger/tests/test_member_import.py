from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.members import Member


def _workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["NO:", "MEMBERS", "CONTACT NO:", "MONTHS"])
    sheet.append([None, None, None, "JAN"])
    sheet.append([1, "First Member", 791678828, 300])
    sheet.append([2, "Second Member", 791678828, 500])
    sheet.append([3, "Missing Number", None, 300])
    sheet.append([None, None, None, None])
    sheet.append([None, "BALANCE DUE (PM):", None, 0])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_import_member_spreadsheet_and_replay(db, group_id):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        first = client.post(
            f"/groups/{group_id}/members/import",
            files={"file": ("members.xlsx", _workbook())},
        )
        assert first.status_code == 200
        assert first.json()["created"] == 3
        assert first.json()["missing_contact_numbers"] == 1
        assert first.json()["shared_contact_numbers"] == 1
        assert db.scalars(select(Member).where(Member.group_id == group_id)).all()[0].contact_number == "791678828"

        replay = client.post(
            f"/groups/{group_id}/members/import",
            files={"file": ("members.xlsx", _workbook())},
        )
        assert replay.status_code == 200
        assert replay.json()["created"] == 0
        assert replay.json()["skipped_existing"] == 3
        assert len(db.scalars(select(Member).where(Member.group_id == group_id)).all()) == 3
    finally:
        app.dependency_overrides.clear()
