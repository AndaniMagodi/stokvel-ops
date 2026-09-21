from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app


def test_group_creation_is_named_and_idempotent(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        first = client.post("/groups", json={"name": "Nyaluwo Stokvel"})
        replay = client.post("/groups", json={"name": "  NYALUWO   stokvel "})
        assert first.status_code == 200
        assert first.json()["created"] is True
        assert replay.status_code == 200
        assert replay.json()["created"] is False
        assert replay.json()["id"] == first.json()["id"]
        assert replay.json()["name"] == "Nyaluwo Stokvel"

        listed = client.get("/groups")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        fetched = client.get(f"/groups/{first.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "Nyaluwo Stokvel"
    finally:
        app.dependency_overrides.clear()
