import os
import tempfile

_dir = tempfile.mkdtemp()
os.environ["ARGUS_DB"] = os.path.join(_dir, "test.db")
os.environ["ARGUS_STEP_DELAY"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # runs startup, which seeds the database
        yield c


def _login(client, user, pw):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="session")
def analyst(client):
    return _login(client, "analyst", "analyst123")


@pytest.fixture(scope="session")
def approver(client):
    return _login(client, "approver", "approver123")


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin", "admin123")
