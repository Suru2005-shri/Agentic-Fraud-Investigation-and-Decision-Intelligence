"""ARGUS API and web server.

Run:  uvicorn backend.main:app --reload
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, engine, graph, retrieval, scoring, security, seed
from .config import FRONTEND_DIR, STEP_DELAY, THRESHOLD


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    try:
        seed.ensure_seeded(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="ARGUS", description="Agentic fraud investigation and decision intelligence", lifespan=lifespan)


# ---------------------------------------------------------------- plumbing
def get_db():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(authorization: str | None = Header(default=None), conn=Depends(get_db)) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    username = security.read_token(token) if token else None
    row = conn.execute("select username, name, role from users where username=?", (username,)).fetchone() if username else None
    if not row:
        raise HTTPException(401, "Sign in to continue.")
    return dict(row)


def guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except engine.RuleError as e:
        raise HTTPException(e.status, str(e))


def _case_or_404(conn, cid: str):
    c = db.get_case(conn, cid)
    if not c:
        raise HTTPException(404, "Case not found.")
    return c


def _hours(opened_at: str) -> int:
    try:
        return max(0, round((datetime.now() - datetime.fromisoformat(opened_at)).total_seconds() / 3600))
    except Exception:
        return 0


# ---------------------------------------------------------------- auth
class Login(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: Login, conn=Depends(get_db)):
    u = conn.execute("select * from users where username=?", (body.username.strip().lower(),)).fetchone()
    if not u or not security.verify_password(body.password, u["pw_hash"], u["salt"]):
        raise HTTPException(401, "Wrong username or password.")
    return {"token": security.make_token(u["username"]), "user": {"username": u["username"], "name": u["name"], "role": u["role"]}}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/health")
def health(conn=Depends(get_db)):
    return {"ok": True, "cases": conn.execute("select count(*) from cases").fetchone()[0], "step_delay": STEP_DELAY}


# ---------------------------------------------------------------- lists
def _list_row(c) -> dict:
    fresh = c["stage"] == "new"
    return {"id": c["id"], "risk": c["triage"] if fresh else c["risk"], "evidence": c["triage_suff"] if fresh else c["suff"],
            "trigger": c["trigger"], "pattern": c["pattern"], "status": "New" if fresh else c["status"], "stage": c["stage"],
            "hours": _hours(c["opened_at"]), "bm": c["bm_no"], "amount": c["amount"], "merchant": c["merchant"]}


@app.get("/api/cases")
def list_cases(user=Depends(current_user), conn=Depends(get_db)):
    rows = conn.execute("select * from cases where stage!='resolved' order by id").fetchall()
    return [_list_row(r) for r in rows]


@app.get("/api/stats")
def stats(user=Depends(current_user), conn=Depends(get_db)):
    act = [_list_row(r) for r in conn.execute("select * from cases where stage!='resolved'").fetchall()]
    return {"active": len(act), "high": sum(1 for c in act if c["risk"] >= 80),
            "awaiting": sum(1 for c in act if c["status"] == "Awaiting evidence"),
            "approval": sum(1 for c in act if c["status"] == "Approval pending"),
            "resolved": conn.execute("select count(*) from cases where stage='resolved'").fetchone()[0]}


@app.get("/api/benchmark")
def benchmark(user=Depends(current_user), conn=Depends(get_db)):
    rows = conn.execute("select bm_no, id, stage, outcome from cases where bm_no is not null order by bm_no").fetchall()
    return [{"no": r["bm_no"], "id": r["id"], "state": "done" if r["stage"] == "resolved" else "progress" if r["stage"] != "new" else "new",
             "outcome": r["outcome"]} for r in rows]


# ---------------------------------------------------------------- case detail
def case_detail(conn, cid: str) -> dict:
    c = _case_or_404(conn, cid)
    tl = conn.execute("select * from timeline where case_id=? order by seq", (cid,)).fetchall()
    lit, depth = {c["account"]}, 1
    for r in tl:
        if r["state"] == "done":
            lit.update(json.loads(r["lit"] or "[]"))
            depth = max(depth, r["depth"] or 1)
    extra = [r["memory_id"] for r in conn.execute("select memory_id from history_links where case_id=? order by ts", (cid,))]
    if extra:
        depth = max(depth, 3)
        for m in extra:
            lit.update([m, "OUT:" + m])
    g = graph.subgraph(conn, c, extra)
    started = c["stage"] != "new"
    priors = scoring.analyze(conn, c)["priors"][:5] if started else []
    if extra:
        seen = {p["id"] for p in priors}
        for p in scoring.rank_priors(conn, c, set(), set(), limit=2000, accounts_only=None):
            if p["id"] in extra and p["id"] not in seen:
                priors.append(p)
    return {
        "id": cid, "stage": c["stage"], "status": "New" if not started else c["status"], "threshold": THRESHOLD,
        "risk": c["risk"] if started else 0, "conf": c["conf"] if started else 0, "unc": c["unc"] if started else 100,
        "suff": c["suff"] if started else 0, "rec": c["rec"], "gap": c["gap"],
        "before": json.loads(c["before_json"]) if c["before_json"] else None,
        "after": json.loads(c["after_json"]) if c["after_json"] else None,
        "add_ev": c["add_ev"], "outcome": c["outcome"], "action": c["action"], "approval": c["approval"],
        "adverse": c["adverse"], "needs_approval": engine.needs_approval(c["rec"]),
        "pattern": c["pattern"], "trigger": c["trigger"], "amount": c["amount"], "merchant": c["merchant"],
        "tx": c["tx"], "account": c["account"], "opened_at": c["opened_at"], "bm": c["bm_no"],
        "timeline": [{"seq": r["seq"], "t": r["title"], "d": r["detail"], "st": r["state"], "time": r["ts"],
                      "depth": r["depth"]} for r in tl],
        "activity": [{"seq": r["seq"], "t": r["text"], "time": r["ts"]}
                     for r in conn.execute("select * from activity where case_id=? order by seq", (cid,))],
        "evidence": [{"seq": r["seq"], "k": r["k"], "v": r["v"], "src": r["src"], "tone": r["tone"]}
                     for r in conn.execute("select * from evidence where case_id=? order by seq", (cid,))],
        "findings": [r["text"] for r in conn.execute("select text from findings where case_id=? order by seq", (cid,))],
        "lit": sorted(lit), "depth": depth, "graph": g, "prior": priors,
        "requests": [{"id": r["id"], "type": r["type"], "status": r["status"]}
                     for r in conn.execute("select * from requests where case_id=? order by id", (cid,))],
    }


@app.get("/api/cases/{cid}")
def get_case(cid: str, user=Depends(current_user), conn=Depends(get_db)):
    return case_detail(conn, cid)


@app.post("/api/cases/{cid}/investigate")
def investigate(cid: str, user=Depends(current_user), conn=Depends(get_db)):
    _case_or_404(conn, cid)
    if engine.begin(conn, cid):
        db.audit(conn, user["username"], user["role"], "open_case", cid, "")
        engine.spawn(engine.investigate, cid, STEP_DELAY)
    return case_detail(conn, cid)


class EvidenceIn(BaseModel):
    type: str


@app.post("/api/cases/{cid}/evidence-requests")
def evidence_request(cid: str, body: EvidenceIn, user=Depends(current_user), conn=Depends(get_db)):
    _case_or_404(conn, cid)
    rid = guard(engine.request_evidence, conn, cid, body.type, user["username"], user["role"], STEP_DELAY)
    if body.type == "analyst":
        engine.spawn(engine.analyst_reply, cid, rid, STEP_DELAY)
    t = security.request_token(rid)
    return {"id": rid, "type": body.type, "token": t, "link": f"/customer.html?r={rid}&t={t}"}


class AnswerIn(BaseModel):
    authorized: bool
    token: str | None = None


def _answer_actor(rid: int, body: AnswerIn, authorization: str | None, conn) -> tuple[str, str]:
    if body.token and body.token == security.request_token(rid):
        return "customer", "customer"
    token = (authorization or "").removeprefix("Bearer ").strip()
    username = security.read_token(token) if token else None
    u = conn.execute("select username, role from users where username=?", (username,)).fetchone() if username else None
    if not u:
        raise HTTPException(401, "This link is not valid.")
    return u["username"] + " (simulating the customer)", u["role"]


@app.post("/api/evidence-requests/{rid}/respond")
def respond(rid: int, body: AnswerIn, authorization: str | None = Header(default=None), conn=Depends(get_db)):
    actor, role = _answer_actor(rid, body, authorization, conn)
    r = conn.execute("select * from requests where id=?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "Evidence request not found.")
    if r["type"] == "analyst":
        raise HTTPException(400, "Analyst requests are answered by the analyst desk.")
    guard(engine.respond, conn, rid, not body.authorized, actor, role)
    return {"ok": True}


@app.get("/api/evidence-requests/{rid}/public")
def public_request(rid: int, t: str, conn=Depends(get_db)):
    if t != security.request_token(rid):
        raise HTTPException(401, "This link is not valid.")
    r = conn.execute("select * from requests where id=?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "Not found.")
    c = db.get_case(conn, r["case_id"])
    return {"type": r["type"], "status": r["status"], "amount": c["amount"], "merchant": c["merchant"],
            "when": c["opened_at"]}


class ApprovalIn(BaseModel):
    decision: str


@app.post("/api/cases/{cid}/approval")
def approval(cid: str, body: ApprovalIn, user=Depends(current_user), conn=Depends(get_db)):
    _case_or_404(conn, cid)
    result = guard(engine.decide_approval, conn, cid, body.decision, user, STEP_DELAY)
    if result == "closing":
        engine.spawn(_close, cid)
    return case_detail(conn, cid)


def _close(conn, cid):
    engine.close_case(conn, cid, 1, STEP_DELAY)


@app.post("/api/cases/{cid}/apply")
def apply_action(cid: str, user=Depends(current_user), conn=Depends(get_db)):
    _case_or_404(conn, cid)
    guard(engine.apply_action, conn, cid, user)
    engine.spawn(_close, cid)
    return case_detail(conn, cid)


class HistoryIn(BaseModel):
    memory_id: str


@app.post("/api/cases/{cid}/history")
def open_history(cid: str, body: HistoryIn, user=Depends(current_user), conn=Depends(get_db)):
    _case_or_404(conn, cid)
    h = db.get_case(conn, body.memory_id)
    if not h or h["stage"] != "resolved":
        raise HTTPException(404, "That case is not in case memory.")
    if not conn.execute("select 1 from history_links where case_id=? and memory_id=?", (cid, body.memory_id)).fetchone():
        conn.execute("insert into history_links values(?,?,?)", (cid, body.memory_id, db.now()))
        conn.commit()
        db.act_add(conn, cid, f"Analyst opened {body.memory_id} in the graph")
    return case_detail(conn, cid)


class NoteIn(BaseModel):
    text: str


@app.post("/api/cases/{cid}/activity")
def add_activity(cid: str, body: NoteIn, user=Depends(current_user), conn=Depends(get_db)):
    _case_or_404(conn, cid)
    db.act_add(conn, cid, body.text[:200])
    return {"ok": True}


# ---------------------------------------------------------------- memory, policy, report
@app.get("/api/memory")
def memory(case: str | None = None, q: str = "", min: int = 0, limit: int = 60,
           user=Depends(current_user), conn=Depends(get_db)):
    c = db.get_case(conn, case) if case else None
    if not c:
        c = db.get_case(conn, seed.HERO) or conn.execute("select * from cases limit 1").fetchone()
    a = scoring.analyze(conn, c)
    items = scoring.rank_priors(conn, c, set(a["mates"]), set(a["ip_mates"]), limit=5000, dev_label=a["device"])
    ql = q.lower().strip()
    items = [i for i in items if i["sim"] >= min and (not ql or ql in (i["id"] + i["pat"] + i["out"]).lower())]
    total = conn.execute("select count(*) from cases where stage='resolved'").fetchone()[0]
    return {"case": c["id"], "total": total, "matches": len(items), "items": items[:limit]}


def _policy_query(c, a) -> str:
    risk = c["risk"] or c["triage"]
    q = (f"{c['pattern']} payment {a['ratio']:.0f} times average amount device linked to "
         f"{len(a['mates'])} unrelated accounts customer authorization block")
    return q + (" low risk release monitoring" if risk < 35 else "")


@app.get("/api/cases/{cid}/policy")
def case_policy(cid: str, user=Depends(current_user), conn=Depends(get_db)):
    c = _case_or_404(conn, cid)
    a = scoring.analyze(conn, c)
    found = retrieval.search(conn, _policy_query(c, a), c["pattern"], k=3)
    answered = conn.execute("select count(*) from requests where case_id=? and status='answered' and type in ('customer','step_up')",
                            (cid,)).fetchone()[0]
    checks = [
        {"state": "ok" if c["amount"] > 50000 else "no", "title": f"Payment amount {engine.inr(c['amount'])}",
         "detail": "Above $50,000, so section 4.2 applies" if c["amount"] > 50000 else "Below the \u20B950,000 trigger for section 4.2"},
        {"state": "ok" if answered else "warn", "title": "Customer authorization established",
         "detail": c["add_ev"] if answered else "Not yet established. Request customer validation or step-up authentication"},
        {"state": "warn" if (engine.needs_approval(c["rec"]) and c["stage"] != "resolved") else "ok",
         "title": "Human approval (section 6.1)",
         "detail": "Required before escalation or blocking" if engine.needs_approval(c["rec"]) else "Not required for the recommended action"},
        {"state": "ok" if c["stage"] == "resolved" else "no", "title": "Case memory record (section 7.3)",
         "detail": "Recorded" if c["stage"] == "resolved" else "Recorded when the case closes"},
    ]
    tid = found[0]["typology"] if found else None
    return {"case": cid, "pattern": c["pattern"], "typology": tid, "sections": found, "checks": checks,
            "all": [dict(r) for r in conn.execute("select id, title, text from policies order by id")]}


@app.get("/api/cases/{cid}/report")
def report(cid: str, user=Depends(current_user), conn=Depends(get_db)):
    c = _case_or_404(conn, cid)
    ev = conn.execute("select k, v from evidence where case_id=? order by seq", (cid,)).fetchall()
    fnd = [r["text"] for r in conn.execute("select text from findings where case_id=? order by seq", (cid,))]
    started = c["stage"] != "new"
    rows = [
        ["Trigger", f"{c['trigger']}. {engine.inr(c['amount'])} at {c['merchant']}, {c['opened_at'].replace('T', ' ')[:16]}"],
        ["Evidence", "\n".join(f"{r['k']}: {r['v']}" for r in ev) or "Not collected yet"],
        ["Findings", ", ".join(fnd) or "None yet"],
        ["Fraud pattern", c["pattern"]],
        ["Risk assessment", f"Risk {c['risk']}. Confidence {c['conf']}%. Evidence sufficiency {c['suff']}%" if started else "Not assessed"],
        ["Uncertainty", f"{c['unc']}% ({scoring.unc_label(c['unc'])})" if started else "Not assessed"],
        ["Additional evidence", c["add_ev"] or "None requested yet"],
        ["Decision", c["rec"] if started else "Not decided"],
        ["Action", c["action"] or "Not taken yet"],
        ["Approval", c["approval"] or "Not requested"],
        ["Outcome", c["outcome"] or "Open"],
    ]
    trail = [{"ts": r["ts"], "actor": r["actor"], "role": r["role"], "action": r["action"], "detail": r["detail"]}
             for r in conn.execute("select * from audit where case_id=? order by id", (cid,))]
    return {"id": cid, "rows": rows, "audit": trail}


# ---------------------------------------------------------------- admin
@app.post("/api/admin/reset")
def reset(user=Depends(current_user), conn=Depends(get_db)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only an admin can reset the demo data.")
    return seed.seed(conn)


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
