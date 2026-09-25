import os,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

_dir=tempfile.mkdtemp()
os.environ["ARGUS_DB"]=os.path.join(_dir,"test.db")
os.environ["ARGUS_DATA_DIR"]=os.environ.get("ARGUS_DATA_DIR",str(Path(__file__).resolve().parents[1]/"data"/"fraud_dataset"))
os.environ["ARGUS_STEP_DELAY"]="0"

import pytest
from fastapi.testclient import TestClient
from backend import db,real_data
from backend.main import app

@pytest.fixture(scope="session")
def client():
    # Use the committed 15 MB benchmark cache so tests are deterministic and fast.
    demo=Path(__file__).resolve().parents[1]/"data"/"argus.db"
    target=os.environ["ARGUS_DB"]
    import shutil
    shutil.copyfile(demo,target)
    with TestClient(app) as c:
        yield c

def login(client,user,pw):
    r=client.post("/api/auth/login",json={"username":user,"password":pw})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

@pytest.fixture(scope="session")
def analyst(client): return login(client,"analyst","analyst123")
@pytest.fixture(scope="session")
def approver(client): return login(client,"approver","approver123")
@pytest.fixture(scope="session")
def admin(client): return login(client,"admin","admin123")
