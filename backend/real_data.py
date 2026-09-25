"""Load a compact, benchmark-focused cache from the full HHG dataset.

TigerGraph receives the full source CSVs via the supplied GSQL loader. ARGUS's local
cache intentionally keeps the 20 benchmark customers, their graph-linked device
windows, and the historical case evidence needed by the UI. This keeps startup fast.
"""
import hashlib,json,zipfile
import pandas as pd
from . import db,policies,security,scoring,graph
from .config import DATA_DIR,DATA_ZIP

USERS=[("analyst","Analyst","analyst","analyst123"),("approver","Approver","approver","approver123"),("admin","Admin","admin","admin123")]
TX_COLS=["TransactionID","TransactionAmt","ProductCD","card1","card5","addr1","addr2","P_emaildomain","R_emaildomain","customer_id","ts","channel","risk_score"]
ID_COLS=["TransactionID","id_15","id_23","id_30","id_31","id_33","id_34","DeviceType","DeviceInfo"]

def _ensure_data():
    if (DATA_DIR/"transactions.csv").exists(): return
    if DATA_ZIP.exists():
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(DATA_ZIP) as z: z.extractall(DATA_DIR)
        return
    raise FileNotFoundError(f"Dataset not found at {DATA_DIR} or {DATA_ZIP}")

def _profiles(df):
    parts=[df[c].fillna("").astype(str).replace("nan","") for c in ("DeviceInfo","id_30","id_31","id_33")]
    z=pd.concat(parts,axis=1)
    return z.apply(lambda r:" | ".join(v.strip() for v in r.tolist() if v.strip()),axis=1).replace("",None)

def _device(p):
    if p is None or pd.isna(p): return None
    return "DEV-"+hashlib.sha1(str(p).encode()).hexdigest()[:12]

def _clear(conn):
    for t in ["entities","edges","transactions","cases","timeline","activity","evidence","findings","requests","history_links","policies","typology","audit","users"]:
        conn.execute(f"delete from {t}")
    conn.commit()

def load(conn,force=False):
    db.init(conn)
    if not force and conn.execute("select count(*) from cases where bm_no is not null").fetchone()[0]==20:
        return {"loaded":True,"cases":20,"message":"already loaded"}
    _ensure_data()
    cp=pd.read_csv(DATA_DIR/"case_pack.csv")
    cc=pd.read_csv(DATA_DIR/"closed_cases_history.csv")
    tx=pd.read_csv(DATA_DIR/"transactions.csv",usecols=TX_COLS)
    ids=pd.read_csv(DATA_DIR/"identity.csv",usecols=ID_COLS)
    ids["profile"]=_profiles(ids); ids["device"]=ids.profile.map(_device)
    df=tx.merge(ids,on="TransactionID",how="left")
    df["sig"]=df.customer_id.astype(str)+"|"+df.card1.astype(str)+"|"+df.card5.astype(str)

    # Preserve exact K1/K2 identifiers wherever the challenge supplies them.
    wanted=set(cp.flagged_txn_id.astype(int))
    wanted |= set(pd.to_numeric(cc.first_fraud_txn_id,errors="coerce").dropna().astype(int))
    wanted_tx=df[df.TransactionID.isin(wanted)][["TransactionID","customer_id","card1","card5"]]
    cmap={}
    for r in cp.itertuples():
        m=wanted_tx[wanted_tx.TransactionID==int(r.flagged_txn_id)]
        if len(m): cmap[f"{m.iloc[0].customer_id}|{m.iloc[0].card1}|{m.iloc[0].card5}"]=r.card_id
    for r in cc.itertuples():
        if pd.isna(r.first_fraud_txn_id): continue
        m=wanted_tx[wanted_tx.TransactionID==int(r.first_fraud_txn_id)]
        if len(m): cmap[f"{m.iloc[0].customer_id}|{m.iloc[0].card1}|{m.iloc[0].card5}"]=r.card_id
    variants=df[["customer_id","sig"]].drop_duplicates()
    for cid,g in variants.groupby("customer_id"):
        used={cmap[s] for s in g.sig if s in cmap}; k=1
        for s in sorted(g.sig):
            if s in cmap: continue
            while f"{cid}-K{k}" in used: k+=1
            cmap[s]=f"{cid}-K{k}"; used.add(f"{cid}-K{k}"); k+=1
    df["card_id"]=df.sig.map(cmap).fillna(df.customer_id.astype(str)+"-K1")

    # Determine the local investigation slice.
    relevant=set(cp.flagged_txn_id.astype(int))
    relevant |= set(df[df.customer_id.isin(set(cp.customer_id))].TransactionID.astype(int))
    # Device-profile neighbours around each benchmark alert.
    dtime=pd.to_datetime(df.ts)
    for r in cp.itertuples():
        rr=df[df.TransactionID==int(r.flagged_txn_id)]
        if not len(rr): continue
        prof=rr.iloc[0].profile
        if not prof: continue
        t=pd.Timestamp(rr.iloc[0].ts)
        m=(df.profile==prof)&(dtime.between(t-pd.Timedelta(days=7),t+pd.Timedelta(days=7)))
        relevant |= set(df.loc[m,"TransactionID"].astype(int))
    # Transactions explicitly named by historical cases for the benchmark cards.
    target_pairs=set(zip(cp.customer_id,cp.card_id))
    for r in cc.itertuples():
        if (r.customer_id,r.card_id) not in target_pairs: continue
        if pd.notna(r.txn_ids):
            relevant |= {int(x) for x in str(r.txn_ids).split("|") if x.isdigit()}

    local=df[df.TransactionID.isin(relevant)].copy()
    out=pd.DataFrame({
      "id":local.TransactionID.astype(str),"account":local.card_id,"customer_id":local.customer_id.astype(str),
      "card_id":local.card_id,"merchant":("Product "+local.ProductCD.astype(str)),"merchant_id":local.ProductCD.astype(str),
      "product_cd":local.ProductCD.astype(str),"device":local.device,"profile":local.profile,"ip":None,
      "amount":local.TransactionAmt.astype(float),"ts":local.ts.astype(str),"channel":local.channel.astype(str),
      "addr1":local.addr1,"addr2":local.addr2,"risk_score":local.risk_score,
      "card1":local.card1,"card5":local.card5,"p_emaildomain":local.P_emaildomain,
      "r_emaildomain":local.R_emaildomain,"id_15":local.id_15,"id_23":local.id_23,"id_30":local.id_30,
      "id_31":local.id_31,"id_33":local.id_33,"id_34":local.id_34,"is_case":0
    })

    _clear(conn)
    conn.execute("PRAGMA synchronous=OFF"); conn.execute("PRAGMA journal_mode=MEMORY")
    for u,name,role,pw in USERS:
        h,s=security.hash_password(pw); conn.execute("insert into users values(?,?,?,?,?)",(u,name,role,h,s))
    for p in policies.POLICIES: conn.execute("insert into policies values(?,?,?)",p)
    for pat,(tid,rs) in policies.TYPOLOGIES.items(): conn.execute("insert into typology values(?,?,?)",(pat,tid,",".join(rs)))
    out.to_sql("transactions",conn,if_exists="append",index=False,chunksize=5000)
    conn.commit()

    # Graph entities/relationships for the local slice.
    customers=set(out.customer_id); cards=set(out.card_id)
    devices=out[["device","profile"]].dropna(subset=["device"]).drop_duplicates().itertuples(index=False)
    regions=set("REG-"+out.addr1.dropna().astype(int).astype(str))
    conn.executemany("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",[(x,"customer",x,"{}") for x in customers])
    conn.executemany("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",[(x,"card",x,"{}") for x in cards])
    conn.executemany("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",[(r.device,"device",r.device,json.dumps({"profile":r.profile})) for r in devices])
    conn.executemany("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",[(x,"region",x[4:],"{}") for x in regions])
    conn.execute("insert or ignore into edges(src,dst,rel) select distinct customer_id,card_id,'owned by' from transactions")
    conn.execute("insert or ignore into edges(src,dst,rel) select distinct card_id,device,'uses' from transactions where device is not null")
    conn.execute("insert or ignore into edges(src,dst,rel) select distinct device,card_id,'used by' from transactions where device is not null")
    conn.execute("insert or ignore into edges(src,dst,rel) select distinct card_id,'REG-'||cast(addr1 as integer),'billed in' from transactions where addr1 is not null")

    # Historical case memory. Only attach a closed case to device profiles that are
    # actually relevant to one of the 20 benchmark investigations.
    bench_ids=set(cp.flagged_txn_id.astype(int))
    bench_profiles=set(df[df.TransactionID.isin(bench_ids)].profile.dropna())
    prof_by_tx=dict(zip(df.TransactionID.astype(int),df.profile))
    for r in cc.itertuples(index=False):
        ids0=[int(x) for x in str(r.txn_ids).split("|") if x.isdigit()] if pd.notna(r.txn_ids) else []
        first=int(r.first_fraud_txn_id) if pd.notna(r.first_fraud_txn_id) else (ids0[0] if ids0 else 0)
        conn.execute("""insert into cases(id,account,tx,trigger,pattern,amount,merchant,merchant_id,opened_at,
          stage,status,outcome,resolved_at,live,ground_truth) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (r.case_id,r.card_id,str(first),f"Historical {r.outcome}",r.pattern,float(r.exposure_usd),
           "historical","historical",r.opened_at,"resolved","Resolved",
           "Confirmed fraud" if r.outcome=="confirmed_fraud" else "Cleared",r.closed_at,0,r.outcome))
        conn.execute("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",
                     (r.case_id,"case",r.case_id,json.dumps({"pattern":r.pattern,"outcome":r.outcome})))
        for tid in ids0:
            prof=prof_by_tx.get(tid)
            if prof in bench_profiles:
                dev=_device(prof)
                conn.execute("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",
                             (dev,"device",dev,json.dumps({"profile":prof})))
                conn.execute("insert or ignore into edges(src,dst,rel) values(?,?,?)",(r.case_id,dev,"case used device"))
    conn.commit()

    def txinfo(tid):
        rr=conn.execute("select product_cd,amount,ts from transactions where id=?",(str(tid),)).fetchone()
        return (("Product "+rr["product_cd"]) if rr else "historical",rr["amount"] if rr else 0,rr["ts"] if rr else "")
    for i,r in enumerate(cp.itertuples(index=False),1):
        prod,amt,ts=txinfo(int(r.flagged_txn_id))
        # benchmark transaction is guaranteed to be in the local slice
        conn.execute("""insert into cases(id,account,tx,trigger,pattern,amount,merchant,merchant_id,opened_at,bm_no)
          values(?,?,?,?,?,?,?,?,?,?)""",(r.case_id,r.card_id,str(int(r.flagged_txn_id)),r.trigger_text,"undetermined",amt,prod,prod,r.opened_at,i))
        conn.execute("insert or ignore into entities(id,type,label,attrs) values(?,?,?,?)",(r.case_id,"case",r.case_id,json.dumps({"benchmark":i})))
    conn.commit()

    # Restore indexes after bulk load.
    for sql in [
      "create index if not exists ix_tx_account on transactions(account,ts)",
      "create index if not exists ix_tx_card on transactions(card_id,ts)",
      "create index if not exists ix_tx_device on transactions(device,ts)",
      "create index if not exists ix_tx_profile on transactions(profile,ts)",
      "create index if not exists ix_tx_region on transactions(addr1,ts)"]:
        conn.execute(sql)
    for r in conn.execute("select * from cases where bm_no is not null").fetchall():
        risk,suff=scoring.triage(conn,r); conn.execute("update cases set triage=?,triage_suff=? where id=?",(risk,suff,r["id"]))
    conn.commit(); conn.execute("PRAGMA synchronous=NORMAL"); conn.execute("PRAGMA journal_mode=WAL"); conn.commit()
    graph.clear_cache()
    return {"loaded":True,"cases":20,"transactions":len(out),"closed_cases":len(cc),"local_cache":len(out)}

def ensure_seeded(conn): return load(conn,False)
def reset(conn): return load(conn,True)
