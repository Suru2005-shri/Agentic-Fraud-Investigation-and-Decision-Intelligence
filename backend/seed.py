"""Builds the demo database: a synthetic graph, resolved case history, policies and 24 open cases.

Run `python -m backend.seed` to (re)create the data. Everything is generated from a fixed
random seed, so the same data appears every time. It is synthetic; replace it with the
challenge dataset (see docs/INTEGRATION.md).
"""
import random
import sys
from datetime import datetime, timedelta

from . import db, engine, graph, policies, scoring, security

MERCHANTS = [  # id, label, category
    ("MC-XYZ", "XYZ", "electronics"), ("MC-BHARAT", "Bharat Electronics", "electronics"),
    ("MC-NOVA", "Novapay Wallet", "prepaid"), ("MC-METRO", "Metro Prepaid", "prepaid"),
    ("MC-MOBI", "Mobile Recharge Hub", "prepaid"), ("MC-QFX", "QuickFX Exchange", "forex"),
    ("MC-ZETA", "Zeta Gift Cards", "gift cards"), ("MC-GIFTO", "Gifto Vouchers", "gift cards"),
    ("MC-ORBIT", "Orbit Gaming", "gaming"), ("MC-URBAN", "Urban Cart", "retail"),
    ("MC-KIRAN", "Kiran Jewellers", "jewellery"), ("MC-SKY", "Skyline Travel", "travel"),
    ("MC-SANA", "Sana Pharmacy", "health"), ("MC-BIGB", "Daily Grocers", "grocery"),
    ("MC-FUEL", "Petro Fuel", "fuel"), ("MC-CAFE", "Cafe Aroma", "food"),
    ("MC-CINE", "CineMax", "entertainment"), ("MC-HOME", "HomeNest Furnishing", "retail"),
    ("MC-BOOK", "Bookworm", "retail"), ("MC-METRO2", "Metro Rides", "travel"),
]
COMMON = [m for m in MERCHANTS if m[2] not in graph.RISKY_CATEGORIES and m[0] != "MC-XYZ"]
RISKY = [m for m in MERCHANTS if m[2] in graph.RISKY_CATEGORIES] + [m for m in MERCHANTS if m[2] == "electronics"]
OTHER_PATTERNS = ["Account takeover", "Card-testing burst", "Synthetic identity", "Rapid cash-out",
                  "Social-engineering payment", "Velocity spike", "First-time high-value merchant", "Travel anomaly",
                  "Chargeback cluster"]
TRIGGER = {
    "Shared-device mule ring": "Device relationship detected", "Shared-device false positive": "Device relationship detected",
    "Account takeover": "Login from unseen device", "Travel anomaly": "Login from unseen device",
    "Card-testing burst": "Velocity spike on new payee", "Velocity spike": "Velocity spike on new payee",
    "Synthetic identity": "Payee linked to prior case", "Rapid cash-out": "High-value first-time merchant",
    "Social-engineering payment": "High-value first-time merchant",
    "First-time high-value merchant": "High-value first-time merchant", "Chargeback cluster": "Chargeback cluster",
}
USERS = [("analyst", "Asha Rao", "analyst", "analyst123"), ("approver", "Vikram Nair", "approver", "approver123"),
         ("admin", "Admin User", "admin", "admin123")]
HERO = "FR-20481"
SEED_USER = {"username": "seed", "name": "Seed batch", "role": "admin"}
TABLES = ["users", "entities", "edges", "transactions", "cases", "timeline", "activity", "evidence", "findings",
          "requests", "history_links", "policies", "typology", "audit"]


def seed(conn, n_accounts: int = 1500, n_hist: int = 1270, rng_seed: int = 20260920) -> dict:
    rnd = random.Random(rng_seed)
    now = datetime.now()
    db.init(conn)
    for t in TABLES:
        conn.execute(f"delete from {t}")
    graph.clear_cache()
    for u, name, role, pw in USERS:
        h, s = security.hash_password(pw)
        conn.execute("insert into users values(?,?,?,?,?)", (u, name, role, h, s))
    for pid, title, text in policies.POLICIES:
        conn.execute("insert into policies values(?,?,?)", (pid, title, text))
    for pat, (tid, ids) in policies.TYPOLOGIES.items():
        conn.execute("insert into typology values(?,?,?)", (pat, tid, ",".join(ids)))

    used: set[str] = {"AC-104821", "AC-207731", "AC-339104", "AC-551876", "CU-3307", "CU-7712", "CU-6120", "CU-8841",
                      "DV-9821", "IP-103.21.44.9", "TX-88213", "TX-70455", "FR-18392", "FR-17102", "FR-16144", "FR-20481"}

    used |= {f"FR-{20481 - i * 137 + (i % 3) * 11}" for i in range(1, 24)}
    used |= {f"FR-{19100 + k * 23}" for k in range(1, 15)}

    def uid(prefix, lo, hi):
        while True:
            x = f"{prefix}-{rnd.randint(lo, hi)}"
            if x not in used:
                used.add(x)
                return x

    def new_ip():
        while True:
            x = f"IP-{rnd.randint(20, 220)}.{rnd.randint(1, 250)}.{rnd.randint(1, 250)}.{rnd.randint(1, 250)}"
            if x not in used:
                used.add(x)
                return x

    accts: list[dict] = []

    def acct(aid=None, cust=None, dev=None, ip=None, mean=None, group="normal"):
        a = {"id": aid or uid("AC", 100000, 999999), "cust": cust or uid("CU", 1000, 9999),
             "dev": dev or uid("DV", 1000, 9999), "ip": ip or new_ip(),
             "mean": mean or rnd.lognormvariate(8.9, 0.45), "group": group}
        accts.append(a)
        return a

    # crafted fraud ring around the headline case
    acct("AC-104821", "CU-3307", "DV-9821", "IP-103.21.44.9", 9000, "hero")
    acct("AC-207731", "CU-7712", "DV-9821", None, 8200, "ring")
    acct("AC-339104", "CU-6120", "DV-9821", "IP-103.21.44.9", 7600, "ring")
    acct("AC-551876", "CU-8841", "DV-9821", None, 9800, "ring")
    # generated rings, benign shared devices and ordinary accounts
    for _ in range(40):
        dev, ip = uid("DV", 1000, 9999), new_ip()
        for j in range(rnd.randint(3, 6)):
            acct(dev=dev, ip=ip if j < 2 else None, group="ring")
    for _ in range(30):
        dev, ip = uid("DV", 1000, 9999), new_ip()
        for _ in range(2):
            acct(dev=dev, ip=ip, group="benign")
    normal: list[dict] = []
    while len(accts) < n_accounts:
        prev = normal[-1] if normal else None
        a = acct(cust=prev["cust"] if prev and rnd.random() < 0.05 else None,
                 ip=rnd.choice(normal)["ip"] if normal and rnd.random() < 0.08 else None)
        normal.append(a)

    for m in MERCHANTS:
        conn.execute("insert into entities values(?,?,?,?)", (m[0], "merchant", m[1], db.dumps({"category": m[2]})))
    seen_c: set[str] = set()
    seen_d: set[str] = set()
    seen_i: set[str] = set()
    for a in accts:
        conn.execute("insert into entities values(?,?,?,?)", (a["id"], "account", a["id"], "{}"))
        if a["cust"] not in seen_c:
            seen_c.add(a["cust"])
            conn.execute("insert into entities values(?,?,?,?)", (a["cust"], "customer", a["cust"], "{}"))
        if a["dev"] not in seen_d:
            seen_d.add(a["dev"])
            conn.execute("insert into entities values(?,?,?,?)", (a["dev"], "device", a["dev"], "{}"))
        if a["ip"] not in seen_i:
            seen_i.add(a["ip"])
            conn.execute("insert into entities values(?,?,?,?)", (a["ip"], "ip", a["ip"][3:], "{}"))
        conn.execute("insert into edges values(?,?,?)", (a["id"], a["cust"], "owned by"))
        conn.execute("insert into edges values(?,?,?)", (a["id"], a["dev"], "used"))
        conn.execute("insert into edges values(?,?,?)", (a["id"], a["ip"], "login from"))

    txn = 100000
    rows = []
    hero_factors = [0.8, 1.2, 0.9, 1.1, 0.85, 1.15, 0.95, 1.05, 0.75, 1.25, 1.0, 1.0]  # averages exactly 9,000
    for a in accts:
        for k in range(12 if a["group"] == "hero" else rnd.randint(8, 12)):
            txn += 1
            if a["group"] == "hero":
                amount = a["mean"] * hero_factors[k]
            elif a["mean"] in (8200, 7600, 9800):
                amount = a["mean"] * rnd.uniform(0.75, 1.25)
            else:
                amount = a["mean"] * rnd.lognormvariate(0, 0.3)
            m = rnd.choice(COMMON)
            rows.append((f"TX-{txn}", a["id"], m[0], a["dev"], a["ip"], round(amount, 2),
                         (now - timedelta(days=rnd.randint(4, 90), hours=rnd.randint(0, 23))).isoformat(timespec="seconds"), 0))
    conn.executemany("insert into transactions values(?,?,?,?,?,?,?,?)", rows)

    by_group = {g: [a for a in accts if a["group"] == g] for g in ("ring", "benign", "normal")}
    by_group["ring"] = [a for a in by_group["ring"] if a["id"] not in ("AC-207731", "AC-339104", "AC-551876")]
    mer = {m[0]: m for m in MERCHANTS}

    def case_row(cid, a, pat, amount, m, opened, tx_id=None, bm=None, resolved=None, outcome=None, gt=None):
        tx_id = tx_id or uid("TX", 10000, 99999)
        conn.execute("insert into transactions values(?,?,?,?,?,?,?,?)",
                     (tx_id, a["id"], m[0], a["dev"], a["ip"], round(amount, 2), opened.isoformat(timespec="seconds"), 1))
        conn.execute("insert into cases(id,account,tx,trigger,pattern,amount,merchant,merchant_id,opened_at,bm_no,ground_truth) "
                     "values(?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, a["id"], tx_id, TRIGGER[pat], pat, round(amount, 2), m[1], m[0], opened.isoformat(timespec="seconds"), bm, gt))
        if resolved:
            fraud = outcome == "Confirmed fraud"
            conf = rnd.randint(88, 97)
            db.set_case(conn, cid, stage="resolved", status="Resolved", risk=rnd.randint(78, 98) if fraud else rnd.randint(22, 58),
                        conf=conf, unc=100 - conf, suff=rnd.randint(88, 98),
                        rec="Escalate to analyst" if fraud else "Allow with monitoring", outcome=outcome,
                        action="Escalated to fraud analyst; transaction held" if fraud else "Transaction released with 30-day monitoring",
                        approval="Approved by fraud approver" if fraud else "Not required by policy",
                        adverse=1 if fraud else 0,
                        add_ev="Customer validation: transaction denied" if fraud else "Customer validation: authorization confirmed",
                        resolved_at=resolved.isoformat(timespec="seconds"))

    # earlier cases recorded against the headline ring
    acc = {a["id"]: a for a in accts}
    case_row("FR-18392", acc["AC-207731"], "Shared-device mule ring", 81200, mer["MC-BHARAT"], datetime(2026, 8, 9, 11, 20),
             resolved=datetime(2026, 8, 11, 16, 5), outcome="Confirmed fraud", gt="fraud")
    case_row("FR-17102", acc["AC-339104"], "Shared-device false positive", 24000, mer["MC-URBAN"], datetime(2026, 7, 25, 10, 0),
             resolved=datetime(2026, 7, 27, 12, 40), outcome="Cleared", gt="legit")
    case_row("FR-16144", acc["AC-551876"], "Rapid cash-out", 79000, mer["MC-ZETA"], datetime(2026, 6, 30, 9, 30),
             tx_id="TX-70455", resolved=datetime(2026, 7, 2, 15, 15), outcome="Confirmed fraud", gt="fraud")

    for _ in range(n_hist - 3):
        cid = uid("FR", 10000, 19999)
        r = rnd.random()
        if r < 0.45:
            a, pat, m = rnd.choice(by_group["ring"]), rnd.choice(["Shared-device mule ring"] * 3 + ["Rapid cash-out"]), rnd.choice(RISKY)
            amount, outcome = a["mean"] * rnd.uniform(4, 11), "Confirmed fraud" if rnd.random() < 0.92 else "Cleared"
        elif r < 0.55:
            a, pat, m = rnd.choice(by_group["benign"]), "Shared-device false positive", rnd.choice(COMMON)
            amount, outcome = a["mean"] * rnd.uniform(1, 2.5), "Cleared" if rnd.random() < 0.95 else "Confirmed fraud"
        else:
            a, pat, m = rnd.choice(by_group["normal"]), rnd.choice(OTHER_PATTERNS), rnd.choice(MERCHANTS)
            amount, outcome = a["mean"] * rnd.uniform(2, 9), "Confirmed fraud" if rnd.random() < 0.55 else "Cleared"
        res = now - timedelta(days=rnd.randint(4, 200), hours=rnd.randint(0, 20))
        case_row(cid, a, pat, amount, m, res - timedelta(days=rnd.randint(1, 3)), resolved=res, outcome=outcome,
                 gt="fraud" if outcome == "Confirmed fraud" else "legit")
    conn.commit()

    # the 24 open cases: the headline case plus 23 more
    case_row("FR-20481", acc["AC-104821"], "Shared-device mule ring", 84500, mer["MC-XYZ"], now - timedelta(hours=2),
             tx_id="TX-88213", bm=15, gt="fraud")
    kinds = ["ring", "ring", "benign", "normal", "normal", "ring", "normal", "benign", "normal", "ring", "normal", "normal",
             "ring", "normal", "ring", "normal", "normal", "benign", "normal", "ring", "normal", "normal", "ring"]
    pools = {k: rnd.sample(v, len(v)) for k, v in by_group.items()}
    active_ids = ["FR-20481"]
    for i, kind in enumerate(kinds, start=1):
        a = pools[kind].pop()
        cid = f"FR-{20481 - i * 137 + (i % 3) * 11}"
        if kind == "ring":
            pat, m, amount, gt = "Shared-device mule ring", rnd.choice(RISKY), a["mean"] * rnd.uniform(5, 10), "fraud"
        elif kind == "benign":
            pat, m, amount, gt = "Shared-device false positive", rnd.choice(COMMON), a["mean"] * rnd.uniform(1.2, 2.8), "legit"
        else:
            pat, m, amount = rnd.choice(OTHER_PATTERNS), rnd.choice(MERCHANTS), a["mean"] * rnd.uniform(1.1, 7)
            gt = "fraud" if rnd.random() < 0.5 else "legit"
        case_row(cid, a, pat, amount, m, now - timedelta(hours=rnd.randint(2, 70), minutes=rnd.randint(0, 59)),
                 bm=15 + i if i <= 5 else None, gt=gt)
        active_ids.append(cid)
    conn.commit()

    # benchmark cases 1-14: investigated and closed by the same engine that runs live cases
    for k in range(1, 15):
        kind = "ring" if k <= 8 else rnd.choice(["normal", "benign", "normal"])
        a = pools[kind].pop()
        if kind == "ring":
            pat, m, amount, gt = "Shared-device mule ring", rnd.choice(RISKY), a["mean"] * rnd.uniform(5, 10), "fraud"
        elif kind == "benign":
            pat, m, amount, gt = "Shared-device false positive", rnd.choice(COMMON), a["mean"] * rnd.uniform(1.2, 2.8), "legit"
        else:
            pat, m, amount = rnd.choice(OTHER_PATTERNS), rnd.choice(MERCHANTS), a["mean"] * rnd.uniform(1.1, 7)
            gt = "fraud" if rnd.random() < 0.5 else "legit"
        cid = f"FR-{19100 + k * 23}"
        case_row(cid, a, pat, amount, m, now - timedelta(days=rnd.randint(3, 14)), bm=k, gt=gt)
        _auto_resolve(conn, cid, gt == "fraud")

    # leave some open cases part-way through so the queue shows different states
    for cid in active_ids[6:9]:
        _run(conn, cid)
    for cid in active_ids[9:11]:
        _run(conn, cid)
        if db.get_case(conn, cid)["stage"] == "gap":
            engine.request_evidence(conn, cid, "customer", "seed", "system", 0)
    for cid in active_ids[11:14]:
        _run(conn, cid)
        if db.get_case(conn, cid)["stage"] == "gap":
            rid = engine.request_evidence(conn, cid, "customer", "seed", "system", 0)
            engine.respond(conn, rid, True, "seed", "system")
    for r in conn.execute("select * from cases where stage!='resolved'").fetchall():
        risk, suff = scoring.triage(conn, r)
        conn.execute("update cases set triage=?, triage_suff=? where id=?", (risk, suff, r["id"]))
    conn.execute("delete from audit")
    conn.commit()
    return {"accounts": len(accts), "cases": conn.execute("select count(*) from cases").fetchone()[0],
            "resolved": conn.execute("select count(*) from cases where stage='resolved'").fetchone()[0]}


def ensure_seeded(conn) -> None:
    """Create the schema and load the demo data the first time the server starts."""
    db.init(conn)
    if not conn.execute("select 1 from users limit 1").fetchone():
        seed(conn)


def _run(conn, cid):
    if engine.begin(conn, cid):
        engine.investigate(conn, cid, 0)


def _auto_resolve(conn, cid, fraud: bool):
    _run(conn, cid)
    if db.get_case(conn, cid)["stage"] == "gap":
        rid = engine.request_evidence(conn, cid, "customer", "seed", "system", 0)
        engine.respond(conn, rid, fraud, "customer", "customer")
    c = db.get_case(conn, cid)
    if c["stage"] == "gap":  # still short of the threshold: use the remaining evidence types
        for t in ("step_up", "analyst"):
            if db.get_case(conn, cid)["stage"] != "gap":
                break
            rid = engine.request_evidence(conn, cid, t, "seed", "system", 0)
            engine.respond(conn, rid, fraud, "customer", "customer")
    c = db.get_case(conn, cid)
    if c["stage"] == "ready":
        if engine.needs_approval(c["rec"]):
            engine.decide_approval(conn, cid, "approve", SEED_USER, 0)
        else:
            engine.apply_action(conn, cid, SEED_USER)
        engine.close_case(conn, cid, live=0, delay=0)


if __name__ == "__main__":
    conn = db.connect()
    print("seeded:", seed(conn))
