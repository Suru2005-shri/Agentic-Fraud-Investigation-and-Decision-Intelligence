import time


def wait_for(client, headers, cid, stages, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        d = client.get(f"/api/cases/{cid}", headers=headers).json()
        if d["stage"] in stages:
            return d
        time.sleep(0.05)
    raise AssertionError(f"{cid} never reached {stages}; last stage {d['stage']}")


def test_requires_login(client):
    assert client.get("/api/cases").status_code == 401
    assert client.post("/api/auth/login", json={"username": "analyst", "password": "nope"}).status_code == 401


def test_dataset_is_loaded(client, analyst):
    s = client.get("/api/stats", headers=analyst).json()
    assert s["resolved"] == 1284 and s["active"] == 24
    cases = client.get("/api/cases", headers=analyst).json()
    hero = next(c for c in cases if c["id"] == "FR-20481")
    assert hero["status"] == "New" and hero["risk"] == 82
    bm = client.get("/api/benchmark", headers=analyst).json()
    assert len(bm) == 20 and sum(1 for b in bm if b["state"] == "done") == 14


def test_full_investigation_flow(client, analyst, approver):
    cid = "FR-20481"
    d = client.post(f"/api/cases/{cid}/investigate", headers=analyst).json()
    d = wait_for(client, analyst, cid, {"gap"})
    # numbers come from the data and the scoring rules
    assert (d["risk"], d["conf"], d["unc"], d["suff"]) == (82, 67, 33, 78)
    assert d["rec"] == "Request customer validation" and d["gap"]
    assert [t["t"] for t in d["timeline"] if t["st"] == "done"][:3] == [
        "Trigger received", "Transaction history analysed", "Graph relationships discovered"]
    assert {"Shared device", "Connected account", "Prior case similarity"} <= set(d["findings"])
    assert d["prior"][0]["id"] == "FR-18392" and d["prior"][0]["sim"] >= 85
    ids = {n["id"] for n in d["graph"]["nodes"]}
    assert {"AC-104821", "DV-9821", "AC-207731", "FR-18392", "OUT:FR-18392"} <= ids

    # evidence request -> customer denies
    r = client.post(f"/api/cases/{cid}/evidence-requests", headers=analyst, json={"type": "customer"})
    assert r.status_code == 200
    rid, token = r.json()["id"], r.json()["token"]
    assert client.get(f"/api/cases/{cid}", headers=analyst).json()["stage"] == "awaiting"
    assert client.post(f"/api/cases/{cid}/evidence-requests", headers=analyst, json={"type": "customer"}).status_code == 409
    pub = client.get(f"/api/evidence-requests/{rid}/public", params={"t": token})
    assert pub.status_code == 200 and pub.json()["amount"] == 84500
    assert client.get(f"/api/evidence-requests/{rid}/public", params={"t": "bad"}).status_code == 401
    # the customer answers through the public link, without signing in
    assert client.post(f"/api/evidence-requests/{rid}/respond", json={"authorized": False, "token": token}).status_code == 200
    d = client.get(f"/api/cases/{cid}", headers=analyst).json()
    assert d["stage"] == "ready" and d["rec"] == "Escalate to analyst"
    assert (d["risk"], d["suff"]) == (96, 96) and d["conf"] >= 90 and d["needs_approval"]
    assert d["before"]["risk"] == 82 and d["after"]["risk"] == 96
    assert d["status"] == "Approval pending"

    # permissions: an analyst cannot approve, an approver can
    r = client.post(f"/api/cases/{cid}/approval", headers=analyst, json={"decision": "approve"})
    assert r.status_code == 403 and "approver" in r.json()["detail"]
    assert client.post(f"/api/cases/{cid}/apply", headers=analyst).status_code == 403
    r = client.post(f"/api/cases/{cid}/approval", headers=approver, json={"decision": "approve"})
    assert r.status_code == 200
    d = wait_for(client, approver, cid, {"resolved"})
    assert d["outcome"] == "Confirmed fraud" and d["approval"].startswith("Approved by")
    assert d["timeline"][-1]["t"] == "Case memory updated"

    # case memory grew, and the resolved case is retrieved for a related case
    assert client.get("/api/stats", headers=analyst).json()["resolved"] == 1285
    mem = client.get("/api/memory", params={"case": "FR-20355"}, headers=analyst).json()
    assert mem["total"] == 1285
    rep = client.get(f"/api/cases/{cid}/report", headers=analyst).json()
    assert dict(rep["rows"])["Outcome"] == "Confirmed fraud"
    assert any(a["action"] == "approve" for a in rep["audit"])


def test_customer_confirms_leads_to_release_without_approval(client, analyst):
    cid = "FR-20355"
    client.post(f"/api/cases/{cid}/investigate", headers=analyst)
    d = wait_for(client, analyst, cid, {"gap", "ready"})
    assert d["stage"] == "gap"
    rid = client.post(f"/api/cases/{cid}/evidence-requests", headers=analyst, json={"type": "step_up"}).json()["id"]
    client.post(f"/api/evidence-requests/{rid}/respond", headers=analyst, json={"authorized": True})
    d = client.get(f"/api/cases/{cid}", headers=analyst).json()
    assert d["risk"] < 55 and not d["needs_approval"] or d["stage"] == "gap"


def test_analyst_request_is_answered_by_the_desk(client, analyst):
    cid = "FR-20070"
    client.post(f"/api/cases/{cid}/investigate", headers=analyst)
    d = wait_for(client, analyst, cid, {"gap", "ready"})
    if d["stage"] == "gap":
        client.post(f"/api/cases/{cid}/evidence-requests", headers=analyst, json={"type": "analyst"})
        d = wait_for(client, analyst, cid, {"ready", "gap"})
        assert any(e["k"] == "Analyst information request" for e in d["evidence"])


def test_low_risk_case_follows_policy_shortcut(client, analyst):
    cases = client.get("/api/cases", headers=analyst).json()
    low = next(c for c in cases if c["stage"] == "new" and c["risk"] < 35)
    client.post(f"/api/cases/{low['id']}/investigate", headers=analyst)
    d = wait_for(client, analyst, low["id"], {"ready"})
    assert d["rec"] == "Allow with monitoring" and not d["needs_approval"]
    assert client.post(f"/api/cases/{low['id']}/apply", headers=analyst).status_code == 200
    assert wait_for(client, analyst, low["id"], {"resolved"})["outcome"] == "Cleared"


def test_reject_and_more_evidence_paths(client, analyst, approver):
    cases = client.get("/api/cases", headers=analyst).json()
    pending = next(c for c in cases if c["status"] == "Approval pending")
    cid = pending["id"]
    r = client.post(f"/api/cases/{cid}/approval", headers=approver, json={"decision": "reject"})
    assert r.status_code == 200 and r.json()["approval"].startswith("Rejected")
    r = client.post(f"/api/cases/{cid}/approval", headers=approver, json={"decision": "more_evidence"})
    assert r.json()["stage"] == "gap"
    assert client.post(f"/api/cases/{cid}/approval", headers=approver, json={"decision": "approve"}).status_code == 409


def test_memory_policy_and_history(client, analyst):
    m = client.get("/api/memory", params={"case": "FR-20481", "min": 60}, headers=analyst).json()
    assert m["items"][0]["sim"] >= 85 and all(i["sim"] >= 60 for i in m["items"])
    p = client.get("/api/cases/FR-20481/policy", headers=analyst).json()
    assert p["sections"][0]["id"] in {"4.2", "8.2"} and p["typology"] == "T-07" and len(p["checks"]) == 4
    d = client.post("/api/cases/FR-20481/history", headers=analyst, json={"memory_id": "FR-16144"}).json()
    assert "FR-16144" in {n["id"] for n in d["graph"]["nodes"]}


def test_only_admin_can_reset(client, analyst, admin):
    assert client.post("/api/admin/reset", headers=analyst).status_code == 403
    assert client.post("/api/admin/reset", headers=admin).status_code == 200
    assert client.get("/api/stats", headers=analyst).json()["resolved"] == 1284
