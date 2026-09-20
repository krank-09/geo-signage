import os
import tempfile

_tmp = tempfile.mkdtemp()
# TEST_DATABASE_URL runs the whole suite against another database (e.g. Postgres) instead of a throwaway SQLite file
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["LOCAL_STORAGE_DIR"] = f"{_tmp}/media"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["OFFLINE_THRESHOLD_SECONDS"] = "2"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def device(client):
    r = client.post("/device/register", json={"device_id": "DEV-001", "registration_token": "DEMO-REG-001"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
