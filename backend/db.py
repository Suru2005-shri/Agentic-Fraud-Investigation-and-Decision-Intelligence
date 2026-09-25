"""SQLite persistence for ARGUS.

The challenge dataset is loaded into this relational cache so the same UI can run
locally while TigerGraph is used as the production graph backend.
"""
import json, os, sqlite3
from datetime import datetime
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
 username TEXT PRIMARY KEY, name TEXT, role TEXT, pw_hash TEXT, salt TEXT);

CREATE TABLE IF NOT EXISTS entities(
 id TEXT PRIMARY KEY, type TEXT, label TEXT, attrs TEXT DEFAULT '{}');

CREATE TABLE IF NOT EXISTS edges(
 src TEXT, dst TEXT, rel TEXT,
 UNIQUE(src,dst,rel));

CREATE INDEX IF NOT EXISTS ix_edges_src ON edges(src,rel);
CREATE INDEX IF NOT EXISTS ix_edges_dst ON edges(dst,rel);
CREATE INDEX IF NOT EXISTS ix_entities_type ON entities(type);

CREATE TABLE IF NOT EXISTS transactions(
 id TEXT PRIMARY KEY,
 account TEXT,
 customer_id TEXT,
 card_id TEXT,
 merchant TEXT,
 merchant_id TEXT,
 product_cd TEXT,
 device TEXT,
 profile TEXT,
 ip TEXT,
 amount REAL,
 ts TEXT,
 channel TEXT,
 addr1 REAL,
 addr2 REAL,
 risk_score REAL,
 card1 REAL,
 card5 REAL,
 p_emaildomain TEXT,
 r_emaildomain TEXT,
 id_15 TEXT,
 id_23 TEXT,
 id_30 TEXT,
 id_31 TEXT,
 id_33 TEXT,
 id_34 TEXT,
 is_case INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_tx_account ON transactions(account,ts);
CREATE INDEX IF NOT EXISTS ix_tx_card ON transactions(card_id,ts);
CREATE INDEX IF NOT EXISTS ix_tx_device ON transactions(device,ts);
CREATE INDEX IF NOT EXISTS ix_tx_profile ON transactions(profile,ts);
CREATE INDEX IF NOT EXISTS ix_tx_region ON transactions(addr1,ts);

CREATE TABLE IF NOT EXISTS cases(
 id TEXT PRIMARY KEY,
 account TEXT,
 tx TEXT,
 trigger TEXT,
 pattern TEXT,
 amount REAL,
 merchant TEXT,
 merchant_id TEXT,
 opened_at TEXT,
 bm_no INTEGER,
 stage TEXT DEFAULT 'new',
 status TEXT DEFAULT 'New',
 risk INTEGER DEFAULT 0,
 conf INTEGER DEFAULT 0,
 unc INTEGER DEFAULT 100,
 suff INTEGER DEFAULT 0,
 rec TEXT DEFAULT 'Gathering signals',
 gap TEXT,
 before_json TEXT,
 after_json TEXT,
 add_ev TEXT,
 outcome TEXT,
 action TEXT,
 approval TEXT,
 adverse INTEGER,
 resolved_at TEXT,
 live INTEGER DEFAULT 0,
 ground_truth TEXT,
 used_types TEXT DEFAULT '',
 triage INTEGER DEFAULT 0,
 triage_suff INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_cases_stage ON cases(stage);
CREATE INDEX IF NOT EXISTS ix_cases_account ON cases(account);

CREATE TABLE IF NOT EXISTS timeline(
 case_id TEXT, seq INTEGER, title TEXT, detail TEXT, state TEXT, ts TEXT, lit TEXT, depth INTEGER);
CREATE TABLE IF NOT EXISTS activity(case_id TEXT, seq INTEGER, text TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS evidence(
 case_id TEXT, seq INTEGER, k TEXT, v TEXT, src TEXT, tone TEXT);
CREATE TABLE IF NOT EXISTS findings(case_id TEXT, seq INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS requests(
 id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, type TEXT, status TEXT,
 adverse INTEGER, created_at TEXT, responded_at TEXT, actor TEXT);
CREATE TABLE IF NOT EXISTS history_links(case_id TEXT, memory_id TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS policies(id TEXT PRIMARY KEY, title TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS typology(pattern TEXT PRIMARY KEY, tid TEXT, policy_ids TEXT);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, role TEXT,
 action TEXT, case_id TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS ix_audit_case ON audit(case_id);
"""

def connect(path=None):
    p=path or DB_PATH
    d=os.path.dirname(p)
    if d: os.makedirs(d,exist_ok=True)
    conn=sqlite3.connect(p,timeout=60,check_same_thread=False)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn

def init(conn):
    conn.executescript(SCHEMA)
    conn.commit()

def now():
    return datetime.now().isoformat(timespec="seconds")

def hhmmss():
    return datetime.now().strftime("%H:%M:%S")

def get_case(conn,cid):
    return conn.execute("select * from cases where id=?",(cid,)).fetchone()

def set_case(conn,cid,**fields):
    if not fields: return
    cols=",".join(f"{k}=?" for k in fields)
    conn.execute(f"update cases set {cols} where id=?",[ *fields.values(),cid])
    conn.commit()

def _next(conn,table,cid):
    return conn.execute(f"select coalesce(max(seq),0)+1 from {table} where case_id=?",(cid,)).fetchone()[0]

def tl_add(conn,cid,title,detail="",state="done",lit=None,depth=None):
    if state=="done":
        conn.execute("delete from timeline where case_id=? and state='pending'",(cid,))
    conn.execute("insert into timeline(case_id,seq,title,detail,state,ts,lit,depth) values(?,?,?,?,?,?,?,?)",
                 (cid,_next(conn,"timeline",cid),title,detail,state,hhmmss() if state=="done" else "",
                  json.dumps(lit or []),depth))
    conn.commit()

def act_add(conn,cid,text):
    conn.execute("insert into activity(case_id,seq,text,ts) values(?,?,?,?)",(cid,_next(conn,"activity",cid),text,hhmmss()))
    conn.commit()

def ev_add(conn,cid,k,v,src,tone=""):
    conn.execute("insert into evidence(case_id,seq,k,v,src,tone) values(?,?,?,?,?,?)",(cid,_next(conn,"evidence",cid),k,v,src,tone))
    conn.commit()

def fnd_add(conn,cid,text):
    if conn.execute("select 1 from findings where case_id=? and text=?",(cid,text)).fetchone(): return
    conn.execute("insert into findings(case_id,seq,text) values(?,?,?)",(cid,_next(conn,"findings",cid),text))
    conn.commit()

def audit(conn,actor,role,action,case_id=None,detail=""):
    conn.execute("insert into audit(ts,actor,role,action,case_id,detail) values(?,?,?,?,?,?)",
                 (now(),actor,role,action,case_id,detail))
    conn.commit()

def dumps(obj):
    return json.dumps(obj,ensure_ascii=False)
