"""The investigation agent: a deterministic, auditable workflow over the graph and policy data.

Each step reads real data, writes its result to the database (timeline, evidence, findings,
meters) and pauses briefly so the interface can show the case as it progresses. There is no
language model here. A model-driven orchestrator can replace `investigate` and call the
same functions in `graph`, `scoring` and `retrieval` as tools (see docs/INTEGRATION.md).
"""
import threading
import time

from . import db, graph, retrieval, scoring
from .config import DB_PATH, STEP_DELAY, THRESHOLD

EVIDENCE_POINTS = {"customer": 18, "step_up": 16, "analyst": 12}
EVIDENCE_NAMES = {"customer": "Customer validation", "step_up": "Step-up authentication",
                  "analyst": "Analyst information request"}
RISK_SHIFT = {"customer": 14, "step_up": 12, "analyst": 10}
APPROVER_ROLES = {"approver", "admin"}


class RuleError(Exception):
    """A request that the case state or the user's role does not allow."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def inr(n: float) -> str:
    s = f"{int(round(n))}"
    head, tail = s[:-3], s[-3:]
    if head:
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return "\u20B9" + s


def needs_approval(rec: str) -> bool:
    return rec == "Escalate to analyst"


def decide(risk: int) -> str:
    return "Escalate to analyst" if risk >= 75 else "Monitor account" if risk >= 55 else "Allow with monitoring"


def _status(stage: str, rec: str) -> str:
    if stage == "awaiting":
        return "Awaiting evidence"
    if stage == "ready" and needs_approval(rec):
        return "Approval pending"
    if stage == "resolved":
        return "Resolved"
    return "Investigating"


def spawn(fn, *args) -> None:
    """Run `fn(conn, *args)` on a background thread with its own connection."""
    path = DB_PATH

    def run():
        conn = db.connect(path)
        try:
            fn(conn, *args)
        finally:
            conn.close()

    threading.Thread(target=run, daemon=True).start()


def begin(conn, cid: str) -> bool:
    cur = conn.execute("update cases set stage='investigating', status='Investigating' where id=? and stage='new'", (cid,))
    conn.commit()
    return cur.rowcount == 1


def investigate(conn, cid: str, delay: float = STEP_DELAY) -> None:
    c = db.get_case(conn, cid)
    a = scoring.analyze(conn, c)
    rp, sp = scoring.parts(a)
    G = graph.subgraph(conn, c)
    N = G["nodes"]
    ids = lambda pred: [n["id"] for n in N if pred(n)]  # noqa: E731

    risk_final = min(99, round(sum(rp.values())))
    top = a["priors"][0] if a["priors"] else None
    dev = a["device"]

    query = (f"{c['pattern']} payment {a['ratio']:.0f} times average amount above 50,000 rupees device linked to "
             f"{len(a['mates'])} unrelated accounts customer authorization block")
    if risk_final < 35:
        query += " low risk release monitoring"
    policy = retrieval.search(conn, query, c["pattern"], k=3)[0]
    first_sentence = policy["text"].split(". ")[0].rstrip(".") + "."

    plan = [
        {"t": "Trigger received",
         "d": f"{c['trigger']}: {inr(c['amount'])} at {c['merchant']}",
         "ev": ("Transaction signal", f"{inr(c['amount'])} is {a['ratio']:.1f}\u00D7 this account's average of {inr(a['avg'])}",
                "Transaction data", "red" if a["ratio"] >= 3 else ""),
         "f": ["Transaction anomaly"] if a["ratio"] >= 2.5 else [],
         "lit": [c["tx"]] + ids(lambda n: n["type"] == "customer" and n["depth"] == 1),
         "act": "Retrieved transaction", "risk": rp["base"] + rp["anomaly"], "suff": sp["transaction"]},
        {"t": "Transaction history analysed",
         "d": f"Compared with {a['n_hist']} earlier transactions" + ("; first payment to this merchant" if a["first_time"] else ""),
         "f": ["First-time merchant"] if a["first_time"] else [],
         "lit": [c["merchant_id"]], "act": "Retrieved transaction history",
         "risk": rp["merchant"], "suff": sp["history"]},
    ]
    if a["mates"]:
        d3 = {"d": f"Device {dev} links to {len(a['mates'])} other accounts",
              "ev": ("Device relationship", f"{len(a['mates'])} connected accounts share this device", "Graph store", "teal"),
              "f": ["Shared device", "Connected account"]}
    elif a["ip_mates"]:
        d3 = {"d": f"IP address shared with {len(a['ip_mates'])} other accounts",
              "ev": ("IP relationship", f"{len(a['ip_mates'])} accounts share an IP address", "Graph store", "teal"),
              "f": ["Shared IP address"]}
    else:
        d3 = {"d": "No shared devices or IP addresses found", "f": []}
    plan.append({"t": "Graph relationships discovered", **d3,
                 "lit": ids(lambda n: n["type"] in ("device", "ip") and n["depth"] == 1)
                        + ids(lambda n: n["type"] == "account" and n["depth"] == 2),
                 "depth": 2 if (a["mates"] or a["ip_mates"]) else None, "act": "Traversed graph",
                 "risk": rp["device"], "suff": sp["graph"]})
    if top:
        plan.append({"t": "Prior case retrieved", "d": f"{top['id']} matches at {top['sim']}% similarity ({top['why']})",
                     "ev": ("Historical case", f"{top['sim']}% similarity to {top['id']} ({top['out'].lower()})", "Case memory", ""),
                     "f": ["Prior case similarity"] if top["sim"] >= 60 else [],
                     "lit": ids(lambda n: n["type"] == "case") + ids(lambda n: n["type"] == "customer" and n["depth"] == 3),
                     "depth": 3, "act": "Retrieved prior cases", "risk": rp["prior"], "suff": sp["prior"]})
    else:
        plan.append({"t": "Prior case retrieved", "d": "No similar resolved cases", "act": "Searched case memory",
                     "risk": 0, "suff": 0})
    plan.append({"t": "Policy evaluated", "d": f"Section {policy['id']} applies to this payment",
                 "ev": ("Policy requirement", f"{policy['title']}: {first_sentence}", "Fraud policy dataset (GraphRAG)", "amber"),
                 "act": "Retrieved policy evidence", "risk": 0, "suff": sp["policy"]})

    risk_acc = suff_acc = 0.0
    for i, s in enumerate(plan):
        if delay:
            time.sleep(delay if i else delay * 0.6)
        risk_acc += s["risk"]
        suff_acc += s["suff"]
        db.tl_add(conn, cid, s["t"], s["d"], "done", s.get("lit"), s.get("depth"))
        db.act_add(conn, cid, s["act"])
        if s.get("ev"):
            db.ev_add(conn, cid, *s["ev"])
        for f in s.get("f", []):
            db.fnd_add(conn, cid, f)
        conf = round(min(0.98, suff_acc) * 100 * 0.86)
        db.set_case(conn, cid, risk=min(99, round(risk_acc)), conf=conf, unc=100 - conf,
                    suff=round(min(0.98, suff_acc) * 100))

    if delay:
        time.sleep(delay)
    suff = round(min(0.98, suff_acc) * 100)
    if risk_final < 35:
        suff = max(suff, 88)  # policy 5.1: low-risk payments do not need customer validation
    conf = round(suff * 0.86)
    if suff < THRESHOLD:
        db.tl_add(conn, cid, "Evidence gap identified", "Customer authorization not established")
        db.act_add(conn, cid, "Evidence sufficiency evaluated")
        db.tl_add(conn, cid, "Customer validation pending", "Waiting for an evidence request", "pending")
        rec = "Request customer validation"
        db.set_case(conn, cid, risk=risk_final, conf=conf, unc=100 - conf, suff=suff, stage="gap", rec=rec,
                    gap="Customer authorization not established.", status="Investigating",
                    before_json=db.dumps({"risk": risk_final, "conf": conf, "rec": rec}))
    else:
        rec = decide(risk_final)
        db.tl_add(conn, cid, "Evidence sufficiency confirmed", f"Evidence meets the {THRESHOLD}% threshold")
        db.act_add(conn, cid, "Evidence sufficiency evaluated")
        db.set_case(conn, cid, risk=risk_final, conf=conf, unc=100 - conf, suff=suff, stage="ready", rec=rec,
                    gap=None, adverse=1 if risk_final >= 55 else 0, status=_status("ready", rec))


def request_evidence(conn, cid: str, rtype: str, actor: str, role: str, delay: float = STEP_DELAY) -> int:
    if rtype not in EVIDENCE_POINTS:
        raise RuleError("Unknown evidence type.", 400)
    c = db.get_case(conn, cid)
    if c["stage"] != "gap":
        raise RuleError("This case is not waiting for an evidence request.")
    used = [u for u in (c["used_types"] or "").split(",") if u]
    if rtype in used:
        raise RuleError(f"{EVIDENCE_NAMES[rtype]} has already been requested for this case.")
    cur = conn.execute("insert into requests(case_id,type,status,created_at,actor) values(?,?,?,?,?)",
                       (cid, rtype, "pending", db.now(), actor))
    conn.commit()
    detail = {"customer": "Sent to the customer app", "step_up": "Challenge sent to the registered device",
              "analyst": "Sent to the analyst desk"}[rtype]
    db.tl_add(conn, cid, f"{EVIDENCE_NAMES[rtype]} requested", detail)
    db.tl_add(conn, cid, "Waiting for response", "", "pending")
    db.act_add(conn, cid, f"{EVIDENCE_NAMES[rtype]} requested")
    db.set_case(conn, cid, stage="awaiting", status="Awaiting evidence", used_types=",".join(used + [rtype]))
    db.audit(conn, actor, role, "request_evidence", cid, EVIDENCE_NAMES[rtype])
    return cur.lastrowid


def analyst_reply(conn, cid: str, rid: int, delay: float) -> None:
    """The analyst desk answers by checking the device network for the case."""
    time.sleep(max(delay * 2.4, 0))
    c = db.get_case(conn, cid)
    a = scoring.analyze(conn, c)
    respond(conn, rid, adverse=len(a["mates"]) >= 2, actor="analyst desk", role="system")


def respond(conn, rid: int, adverse: bool, actor: str, role: str) -> None:
    r = conn.execute("select * from requests where id=?", (rid,)).fetchone()
    if not r or r["status"] != "pending":
        raise RuleError("This evidence request has already been answered.")
    cid, rtype = r["case_id"], r["type"]
    c = db.get_case(conn, cid)
    conn.execute("update requests set status='answered', adverse=?, responded_at=?, actor=? where id=?",
                 (1 if adverse else 0, db.now(), actor, rid))
    conn.commit()
    if rtype == "analyst":
        text = ("Analyst confirmed device reuse across unrelated accounts" if adverse
                else "Analyst found no link between the accounts on this device")
    elif rtype == "customer":
        text = "Customer denied authorizing the transaction" if adverse else "Customer confirmed authorizing the transaction"
    else:
        text = "Step-up authentication failed" if adverse else "Step-up authentication passed"

    before = {"risk": c["risk"], "conf": c["conf"], "rec": c["rec"]}
    suff = min(98, c["suff"] + EVIDENCE_POINTS[rtype])
    risk = c["risk"]
    if adverse:
        risk = min(99, risk + RISK_SHIFT[rtype])
        db.fnd_add(conn, cid, "Authorization denied" if rtype != "analyst" else "Analyst confirmed device reuse")
    else:
        risk = max(18, round(risk * 0.45))
        db.fnd_add(conn, cid, "Authorization confirmed" if rtype != "analyst" else "Analyst found no link")
    direct = rtype in ("customer", "step_up")
    consistent = direct and ((adverse and risk >= 75) or (not adverse and risk < 55))
    conf = min(98, round(suff * 0.86) + (10 if consistent else 0))
    used = {u for u in (c["used_types"] or "").split(",") if u}
    exhausted = len(used) >= 3

    db.tl_add(conn, cid, "Evidence received", text)
    db.act_add(conn, cid, f"Received {EVIDENCE_NAMES[rtype].lower()}")
    db.ev_add(conn, cid, EVIDENCE_NAMES[rtype], text, "Analyst response" if rtype == "analyst" else "Customer response",
              "red" if adverse else "teal")
    if suff >= THRESHOLD or exhausted:
        rec = decide(risk) if suff >= THRESHOLD else "Escalate to analyst"
        stage, gap = "ready", None
        if suff < THRESHOLD:
            db.tl_add(conn, cid, "Evidence still insufficient", "Every evidence request has been used, so the case goes to an analyst")
    else:
        rec, stage = "Request additional evidence", "gap"
        gap = f"Evidence is still below the {THRESHOLD}% threshold."
        db.tl_add(conn, cid, "Evidence still insufficient", gap)
        db.tl_add(conn, cid, "Additional evidence pending", "Waiting for another evidence request", "pending")
    db.tl_add(conn, cid, "Assessment updated",
              f"Risk {before['risk']} \u2192 {risk}, confidence {before['conf']}% \u2192 {conf}%")
    if rec != before["rec"]:
        db.tl_add(conn, cid, "Recommendation changed", f"{before['rec']} \u2192 {rec}")
    db.act_add(conn, cid, "Evidence sufficiency re-evaluated")
    db.set_case(conn, cid, risk=risk, conf=conf, unc=100 - conf, suff=suff, rec=rec, stage=stage, gap=gap,
                adverse=1 if adverse else 0, add_ev=f"{EVIDENCE_NAMES[rtype]}: {text}",
                before_json=db.dumps(before), after_json=db.dumps({"risk": risk, "conf": conf, "rec": rec}),
                status=_status(stage, rec))
    db.audit(conn, actor, role, "evidence_response", cid, text)


def decide_approval(conn, cid: str, decision: str, user: dict, delay: float = STEP_DELAY) -> str:
    c = db.get_case(conn, cid)
    if c["stage"] != "ready" or not needs_approval(c["rec"]):
        raise RuleError("This case has no action waiting for approval.")
    if user["role"] not in APPROVER_ROLES:
        raise RuleError(f"Your role ({user['role']}) cannot approve or reject actions. Sign in as an approver.", 403)
    name = user["name"]
    if decision == "approve":
        db.set_case(conn, cid, approval=f"Approved by {name}", action="Escalated to fraud analyst; transaction held",
                    stage="closing", status="Investigating")
        db.act_add(conn, cid, f"Approved by {name}")
        db.audit(conn, user["username"], user["role"], "approve", cid, c["rec"])
        return "closing"
    if decision == "reject":
        db.set_case(conn, cid, approval=f"Rejected by {name}")
        db.tl_add(conn, cid, "Approval rejected", f"Rejected by {name}; the recommendation stays open")
        db.act_add(conn, cid, "Approval rejected")
        db.audit(conn, user["username"], user["role"], "reject", cid, c["rec"])
        return "ready"
    if decision == "more_evidence":
        db.tl_add(conn, cid, "More evidence requested", f"Requested by {name} before approving", "done")
        db.tl_add(conn, cid, "Additional evidence pending", "Waiting for an evidence request", "pending")
        db.act_add(conn, cid, "Approver asked for more evidence")
        db.set_case(conn, cid, stage="gap", rec="Request additional evidence", suff=min(c["suff"], 80), used_types="",
                    gap="The approver asked for further evidence before deciding.", status="Investigating")
        db.audit(conn, user["username"], user["role"], "request_more_evidence", cid, "")
        return "gap"
    raise RuleError("Decision must be approve, reject or more_evidence.", 400)


def apply_action(conn, cid: str, user: dict) -> str:
    c = db.get_case(conn, cid)
    if c["stage"] != "ready":
        raise RuleError("This case has no action ready to apply.")
    if needs_approval(c["rec"]):
        raise RuleError("This action needs human approval.", 403)
    action = "Account placed on monitoring" if c["rec"] == "Monitor account" else "Transaction released with 30-day monitoring"
    db.set_case(conn, cid, action=action, approval="Not required by policy", stage="closing", status="Investigating")
    db.act_add(conn, cid, "Action applied: " + action)
    db.audit(conn, user["username"], user["role"], "apply_action", cid, action)
    return "closing"


def close_case(conn, cid: str, live: int = 1, delay: float = STEP_DELAY) -> None:
    c = db.get_case(conn, cid)
    appr = needs_approval(c["rec"])
    items = ["Investigation complete", "Evidence recorded", "Decision recorded", "Action recorded",
             "Approval recorded" if appr else "Approval not required", "Case memory updated"]
    for t in items:
        if delay:
            time.sleep(delay * 0.65)
        db.tl_add(conn, cid, t, "")
        db.act_add(conn, cid, t)
    fraud = c["adverse"] == 1 or (c["adverse"] is None and c["risk"] >= 75)
    db.set_case(conn, cid, outcome="Confirmed fraud" if fraud else "Cleared", stage="resolved", status="Resolved",
                resolved_at=db.now(), live=live)
    db.audit(conn, "system", "system", "resolve", cid, "Confirmed fraud" if fraud else "Cleared")
