import json,time
from pathlib import Path

def wait_for(client,h,cid,states,timeout=8):
    end=time.time()+timeout
    while time.time()<end:
        d=client.get(f"/api/cases/{cid}",headers=h).json()
        if d.get("stage") in states:return d
        time.sleep(.05)
    raise AssertionError(d)

def test_requires_login(client):
    assert client.get("/api/cases").status_code==401
    assert client.post("/api/auth/login",json={"username":"analyst","password":"bad"}).status_code==401

def test_benchmark_is_real_dataset(client,analyst):
    cases=client.get("/api/cases",headers=analyst).json()
    assert len(cases)==20
    assert {c["id"] for c in cases}=={f"HHG-{i:03d}" for i in range(1,21)}
    stats=client.get("/api/stats",headers=analyst).json()
    assert stats["resolved"]>=5500

def test_customer_report_path(client,analyst,approver):
    cid="HHG-006"
    client.post(f"/api/cases/{cid}/investigate",headers=analyst)
    d=wait_for(client,analyst,cid,{"ready"})
    assert d["pattern"]=="card_not_present_new_device"
    assert d["needs_approval"]
    assert d["rec"]=="Block card"
    assert client.post(f"/api/cases/{cid}/approval",headers=analyst,json={"decision":"approve"}).status_code==403
    r=client.post(f"/api/cases/{cid}/approval",headers=approver,json={"decision":"approve"})
    assert r.status_code==200
    d=wait_for(client,approver,cid,{"resolved"})
    assert d["outcome"]=="Confirmed fraud"
    assert any(x["t"]=="Case memory updated" for x in d["timeline"])

def test_uncertain_case_requests_customer_validation(client,analyst):
    cid="HHG-005"
    client.post(f"/api/cases/{cid}/investigate",headers=analyst)
    d=wait_for(client,analyst,cid,{"gap"})
    assert d["rec"]=="Request customer validation"
    r=client.post(f"/api/cases/{cid}/evidence-requests",headers=analyst,json={"type":"customer"})
    assert r.status_code==200
    rid,token=r.json()["id"],r.json()["token"]
    assert client.get(f"/api/evidence-requests/{rid}/public",params={"t":token}).status_code==200
    assert client.post(f"/api/evidence-requests/{rid}/respond",json={"authorized":False,"token":token}).status_code==200
    d=client.get(f"/api/cases/{cid}",headers=analyst).json()
    assert d["stage"]=="ready" and d["rec"]=="Block card" and d["adverse"]

def test_analyst_trigger_uses_analyst_evidence(client,analyst):
    cid="HHG-014"
    client.post(f"/api/cases/{cid}/investigate",headers=analyst)
    d=wait_for(client,analyst,cid,{"gap"})
    assert d["rec"]=="Request analyst information"
    r=client.post(f"/api/cases/{cid}/evidence-requests",headers=analyst,json={"type":"analyst"})
    assert r.status_code==200
    d=wait_for(client,analyst,cid,{"ready"})
    assert any(e["k"]=="Analyst information request" for e in d["evidence"])

def test_submission_has_20_valid_json_files():
    files=sorted((Path(__file__).resolve().parents[1]/"submission"/"cases").glob("HHG-*.json"))
    assert len(files)==20
    for f in files:
        d=json.loads(f.read_text())
        assert d["case_id"]==f.stem
        assert "next_best_actions" in d and "initial" in d["next_best_actions"] and "final" in d["next_best_actions"]
        assert "sar" in d and isinstance(d["sar"]["file"],bool)
