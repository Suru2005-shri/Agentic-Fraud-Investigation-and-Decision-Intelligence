"""Agent workflow, evidence loop and approval gate."""
import threading,time
from . import db,graph,scoring,retrieval
from .config import DB_PATH,STEP_DELAY,THRESHOLD

EVIDENCE_POINTS={"customer":18,"step_up":16,"analyst":12}
EVIDENCE_NAMES={"customer":"Customer validation","step_up":"Step-up authentication","analyst":"Analyst information request"}
APPROVER_ROLES={"approver","admin"}

class RuleError(Exception):
    def __init__(self,message,status=409):
        super().__init__(message); self.status=status

def inr(n):
    return "$"+format(float(n),",.2f")

def needs_approval(rec):
    return rec in {"Block card","Escalate to analyst"}

def decide(risk,prob=None):
    p=prob if prob is not None else risk/99
    if p>=.85: return "Block card"
    if p>=.70: return "Create fraud case"
    if p>=.45: return "Request customer validation"
    return "Allow transaction with monitoring"

def _status(stage,rec):
    if stage=="awaiting": return "Awaiting evidence"
    if stage=="ready" and needs_approval(rec): return "Approval pending"
    if stage=="resolved": return "Resolved"
    return "Investigating"

def spawn(fn,*args):
    def run():
        conn=db.connect(DB_PATH)
        try: fn(conn,*args)
        finally: conn.close()
    threading.Thread(target=run,daemon=True).start()

def _write_case_memory(conn,cid):
    c=db.get_case(conn,cid)
    if not c: return
    conn.execute("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",
                 (cid,"case",cid,db.dumps({"outcome":c["outcome"],"pattern":c["pattern"],"exposure":c["amount"]})))
    conn.execute("insert or ignore into edges(src,dst,rel) values(?,?,?)",(cid,c["account"],"case on"))
    conn.execute("insert or ignore into edges(src,dst,rel) values(?,?,?)",(cid,c["tx"],"affected transaction"))
    conn.commit()

def begin(conn,cid):
    cur=conn.execute("update cases set stage='investigating',status='Investigating' where id=? and stage='new'",(cid,))
    conn.commit(); return cur.rowcount==1

def investigate(conn,cid,delay=STEP_DELAY):
    c=db.get_case(conn,cid)
    a=scoring.analyze(conn,c)
    p=scoring.parts(a)
    if c["pattern"]=="undetermined":
        db.set_case(conn,cid,pattern=a["pattern"])
        c=db.get_case(conn,cid)
    # The trigger/customer report is already evidence; do not fabricate an answer.
    steps=[
      ("Trigger received",f"{c['trigger']}",("Trigger",c["trigger"],"case pack","amber")),
      ("Transaction history analysed",
       f"Reviewed {a['hist_count']} prior transactions; flagged amount is {inr(c['amount'])}, {a['ratio']:.1f}× the historical average.",
       ("History",f"{a['hist_count']} prior transactions; amount ratio {a['ratio']:.1f}×","graph:card_history","")),
      ("Graph relationships discovered",
       f"{len(a['shared_accounts'])} other cards share the observed device profile within ±7 days." if a["profile"] else "No usable device profile is available for this transaction.",
       ("Device relationship",f"{len(a['shared_accounts'])} connected cards on the device profile" if a["profile"] else "No device profile","graph:device_neighbors","teal")),
      ("Prior case memory retrieved",
       f"{len(a['priors'])} historical cases ranked; top match {a['priors'][0]['id']} at {a['priors'][0]['sim']}%." if a["priors"] else "No useful prior case matched.",
       ("Case memory",a["priors"][0]["id"] if a["priors"] else "No match","graph:case_memory","")),
      ("Pattern assessment",
       f"Pattern assessed as {a['pattern']}. Evidence includes new_device={a['new_device']}, online_burst={a['burst_count']}, out_of_region={a['out_region']}, card_testing={a['card_testing']}.",
       ("Pattern",a["pattern"],"agent:pattern_classifier","amber")),
    ]
    if a["strong_shared"]:
        db.fnd_add(conn,cid,"Specific device profile is shared across multiple cards")
    if a["new_device"]: db.fnd_add(conn,cid,"Identity record marks the device as New")
    if a["card_testing"]: db.fnd_add(conn,cid,"Card-testing sequence detected")
    if a["out_region"]: db.fnd_add(conn,cid,"Card-present transaction uses a region not previously seen on this card")
    if a["same_fraud"]>=2: db.fnd_add(conn,cid,f"{a['same_fraud']} prior confirmed-fraud cases exist on this card")
    if a["customer_report"]: db.fnd_add(conn,cid,"Customer dispute is part of the trigger evidence")
    for i,(title,detail,ev) in enumerate(steps):
        if delay: time.sleep(delay if i else delay*.5)
        db.tl_add(conn,cid,title,detail,"done",[],i+1)
        db.act_add(conn,cid,"Agent: "+title)
        db.ev_add(conn,cid,*ev)
    # Update meters.
    risk=p["risk"]; conf=p["confidence"]; suff=p["suff"]
    # Existing customer denial is decisive enough to move to ready; other risk-score cases may request validation.
    analyst_trigger="analyst request" in str(c["trigger"]).lower()
    if analyst_trigger:
        rec="Request analyst information"; stage="gap"
        db.tl_add(conn,cid,"Analyst evidence required","The trigger explicitly asks for connected-card investigation.")
        db.tl_add(conn,cid,"Analyst information pending","Waiting for an evidence request","pending")
    elif a["customer_report"]:
        rec="Block card" if a["probability"]>=.55 else "Request customer validation"
        stage="ready" if rec!="Request customer validation" else "gap"
        if rec=="Block card": db.tl_add(conn,cid,"Customer denial recognized", "The trigger itself is a customer dispute; no second denial is required.")
    elif a["probability"]<.70:
        rec="Request customer validation"; stage="gap"
        db.tl_add(conn,cid,"Evidence gap identified","A risk signal alone is insufficient; customer authorization is required.")
        db.tl_add(conn,cid,"Customer validation pending","Waiting for an evidence request","pending")
    else:
        rec=decide(risk,a["probability"]); stage="ready"
        db.tl_add(conn,cid,"Evidence sufficiency assessed",f"Current evidence supports {rec}.")
    db.set_case(conn,cid,risk=risk,conf=conf,unc=100-conf,suff=suff,rec=rec,stage=stage,
                status=_status(stage,rec),gap="Customer authorization not established." if stage=="gap" else None,
                adverse=1 if a["customer_report"] else 0,
                before_json=db.dumps({"risk":risk,"conf":conf,"rec":rec}))
    db.audit(conn,"agent","system","investigate",cid,f"pattern={a['pattern']}; probability={a['probability']:.2f}")

def request_evidence(conn,cid,rtype,actor,role,delay=STEP_DELAY):
    if rtype not in EVIDENCE_POINTS: raise RuleError("Unknown evidence type.",400)
    c=db.get_case(conn,cid)
    if c["stage"]!="gap": raise RuleError("This case is not waiting for an evidence request.")
    used=[u for u in (c["used_types"] or "").split(",") if u]
    if rtype in used: raise RuleError(f"{EVIDENCE_NAMES[rtype]} already requested.")
    cur=conn.execute("insert into requests(case_id,type,status,created_at,actor) values(?,?,?,?,?)",
                     (cid,rtype,"pending",db.now(),actor)); conn.commit()
    detail={"customer":"Customer validation link created","step_up":"Step-up challenge created","analyst":"Analyst evidence task created"}[rtype]
    db.tl_add(conn,cid,f"{EVIDENCE_NAMES[rtype]} requested",detail)
    db.tl_add(conn,cid,"Waiting for response","","pending")
    db.act_add(conn,cid,f"Requested {EVIDENCE_NAMES[rtype]}")
    db.set_case(conn,cid,stage="awaiting",status="Awaiting evidence",used_types=",".join(used+[rtype]))
    db.audit(conn,actor,role,"request_evidence",cid,EVIDENCE_NAMES[rtype])
    return cur.lastrowid

def analyst_reply(conn,cid,rid,delay):
    if delay: time.sleep(delay*2)
    c=db.get_case(conn,cid); a=scoring.analyze(conn,c)
    respond(conn,rid,a["strong_shared"] or a["same_fraud"]>=1,"analyst desk","system")

def respond(conn,rid,adverse,actor,role):
    r=conn.execute("select * from requests where id=?",(rid,)).fetchone()
    if not r or r["status"]!="pending": raise RuleError("Evidence request already answered.")
    cid,rtype=r["case_id"],r["type"]; c=db.get_case(conn,cid); a=scoring.analyze(conn,c)
    conn.execute("update requests set status='answered',adverse=?,responded_at=?,actor=? where id=?",
                 (1 if adverse else 0,db.now(),actor,rid)); conn.commit()
    if rtype=="customer": text="Customer denied authorizing the transaction" if adverse else "Customer confirmed authorizing the transaction"
    elif rtype=="step_up": text="Step-up authentication failed" if adverse else "Step-up authentication passed"
    else: text="Analyst confirmed a connected-device relationship" if adverse else "Analyst found no adverse connected-device relationship"
    db.tl_add(conn,cid,"Evidence received",text); db.act_add(conn,cid,"Received "+EVIDENCE_NAMES[rtype].lower())
    db.ev_add(conn,cid,EVIDENCE_NAMES[rtype],text,"Customer" if rtype=="customer" else "Analyst","red" if adverse else "teal")
    before={"risk":c["risk"],"conf":c["conf"],"rec":c["rec"]}
    # Adjust probability without pretending this is a model label.
    p=a["probability"]
    p=min(.98,p+.22) if adverse else max(.05,p-.35)
    risk=round(p*99); conf=min(98,c["conf"]+EVIDENCE_POINTS[rtype]//2)
    if adverse:
        db.fnd_add(conn,cid,"Authorization denied" if rtype!="analyst" else "Adverse analyst evidence")
    else:
        db.fnd_add(conn,cid,"Authorization confirmed" if rtype!="analyst" else "No adverse analyst link")
    if not adverse:
        rec="Close no fraud"; stage="ready"; gap=None
    elif p>=.70:
        rec="Block card"; stage="ready"; gap=None
    else:
        rec="Request additional evidence"; stage="gap"; gap="Evidence remains below the decision threshold."
        db.tl_add(conn,cid,"Additional evidence pending",gap,"pending")
    db.tl_add(conn,cid,"Assessment updated",f"Fraud probability changed to {p:.2f}; recommendation is {rec}.")
    if rec!=before["rec"]: db.tl_add(conn,cid,"Recommendation changed",f"{before['rec']} → {rec}")
    db.set_case(conn,cid,risk=risk,conf=conf,unc=100-conf,suff=min(98,c["suff"]+EVIDENCE_POINTS[rtype]),
                rec=rec,stage=stage,gap=gap,adverse=1 if adverse else 0,
                add_ev=f"{EVIDENCE_NAMES[rtype]}: {text}",
                before_json=db.dumps(before),after_json=db.dumps({"risk":risk,"conf":conf,"rec":rec}),
                status=_status(stage,rec))
    db.audit(conn,actor,role,"evidence_response",cid,text)

def decide_approval(conn,cid,decision,user,delay=STEP_DELAY):
    c=db.get_case(conn,cid)
    if c["stage"]!="ready" or not needs_approval(c["rec"]): raise RuleError("No action is waiting for approval.")
    if user["role"] not in APPROVER_ROLES: raise RuleError("Your role cannot approve or reject this action.",403)
    if decision=="approve":
        db.set_case(conn,cid,approval=f"Approved by {user['name']}",action="BLOCK_CARD / escalate as required",stage="closing",status="Investigating")
        db.act_add(conn,cid,f"Approved by {user['name']}")
        db.audit(conn,user["username"],user["role"],"approve",cid,c["rec"]); return "closing"
    if decision=="reject":
        db.set_case(conn,cid,approval=f"Rejected by {user['name']}")
        db.audit(conn,user["username"],user["role"],"reject",cid,c["rec"]); return "ready"
    if decision=="more_evidence":
        db.set_case(conn,cid,stage="gap",rec="Request additional evidence",suff=min(c["suff"],80),
                    used_types="",gap="Approver requested more evidence.",status="Investigating")
        db.audit(conn,user["username"],user["role"],"request_more_evidence",cid,""); return "gap"
    raise RuleError("Decision must be approve, reject or more_evidence.",400)

def apply_action(conn,cid,user):
    c=db.get_case(conn,cid)
    if c["stage"]!="ready": raise RuleError("No action is ready.")
    if needs_approval(c["rec"]): raise RuleError("This action needs human approval.",403)
    action="Transaction released with monitoring" if "Close" not in c["rec"] else "Alert closed as legitimate"
    db.set_case(conn,cid,action=action,approval="Not required by policy",stage="closing",status="Investigating")
    db.act_add(conn,cid,"Action applied: "+action); db.audit(conn,user["username"],user["role"],"apply_action",cid,action)
    return "closing"

def close_case(conn,cid,live=1,delay=STEP_DELAY):
    c=db.get_case(conn,cid)
    fraud=(c["adverse"]==1 or (c["rec"]=="Block card"))
    items=["Investigation complete","Evidence recorded","Decision recorded","Action recorded","Approval recorded" if needs_approval(c["rec"]) else "Approval not required","Case memory updated"]
    for t in items:
        if delay: time.sleep(delay*.4)
        db.tl_add(conn,cid,t); db.act_add(conn,cid,t)
    outcome="Confirmed fraud" if fraud else "Cleared"
    db.set_case(conn,cid,outcome=outcome,stage="resolved",status="Resolved",resolved_at=db.now(),live=live)
    _write_case_memory(conn,cid)
    db.audit(conn,"system","system","resolve",cid,outcome)
