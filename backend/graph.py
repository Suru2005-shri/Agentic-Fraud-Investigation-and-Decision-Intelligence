"""Graph access layer.

The local adapter uses SQLite relationship tables. The same function names are the
seam used by the TigerGraph/MCP adapter, so the agent does not depend on SQL details.
"""
import json
from .config import DATA_DIR

_cat_cache={}
RISKY_CATEGORIES={"R","H","C","S"}  # ProductCD is a Vesta product code, not a merchant category.

def clear_cache(): _cat_cache.clear()

def merchant_category(conn, merchant_id):
    # In this dataset ProductCD is the only merchant-like categorical field exposed.
    return str(merchant_id or "unknown")

def devices_of(conn,acct):
    return [r[0] for r in conn.execute("select dst from edges where src=? and rel='uses'",(acct,)).fetchall()]

def ips_of(conn,acct):
    return []

def device_accounts(conn,dev):
    return [r[0] for r in conn.execute("select dst from edges where src=? and rel='used by'",(dev,)).fetchall()]

def ip_accounts(conn,ip):
    return []

def owner_of(conn,acct):
    r=conn.execute("select src from edges where dst=? and rel='owned by'",(acct,)).fetchone()
    return r[0] if r else None

def region_accounts(conn,region):
    return [r[0] for r in conn.execute(
        "select distinct account from transactions where addr1=?",(region,)).fetchall()]

def card_transactions(conn,acct,start=None,end=None,limit=None):
    q="select * from transactions where account=?"
    args=[acct]
    if start: q+=" and ts>=?"; args.append(start)
    if end: q+=" and ts<=?"; args.append(end)
    q+=" order by ts"
    if limit: q+=f" limit {int(limit)}"
    return conn.execute(q,args).fetchall()

def has_confirmed_fraud(conn,acct):
    return conn.execute("select 1 from cases where account=? and stage='resolved' and outcome='Confirmed fraud' limit 1",(acct,)).fetchone() is not None

def shared_profiles(conn,profile,exclude_account=None,start=None,end=None):
    if not profile: return []
    q="select distinct account,card_id,id from transactions where profile=?"
    args=[profile]
    if exclude_account: q+=" and account!=?"; args.append(exclude_account)
    if start: q+=" and ts>=?"; args.append(start)
    if end: q+=" and ts<=?"; args.append(end)
    return conn.execute(q,args).fetchall()

def subgraph(conn,c,extra_ids=()):
    from . import scoring
    acct=c["account"]
    nodes={}; edges=[]

    def add(nid,typ,label,depth,risk="low",tx=0):
        if nid and nid not in nodes:
            nodes[nid]={"id":nid,"type":typ,"label":label,"depth":depth,"risk":risk,"tx":tx}
    def link(a,b,label):
        if a in nodes and b in nodes and a!=b and not any(e["a"]==a and e["b"]==b for e in edges):
            edges.append({"a":a,"b":b,"label":label})

    tx=conn.execute("select * from transactions where id=?",(c["tx"],)).fetchone()
    add(acct,"card",acct,0,"high" if (c["risk"] or c["triage"] or 0)>=75 else "med",
        conn.execute("select count(*) from transactions where account=?",(acct,)).fetchone()[0])
    customer=owner_of(conn,acct)
    if customer: add(customer,"customer",customer,1); link(acct,customer,"owned by")
    add(c["tx"],"tx",c["tx"],1,"high" if (c["risk"] or 0)>=55 else "med",1); link(acct,c["tx"],"used for")
    if tx:
        add("PRODUCT:"+str(tx["product_cd"]),"merchant",f"Product {tx['product_cd']}",2,"med",0); link(c["tx"],"PRODUCT:"+str(tx["product_cd"]),"product")
        if tx["addr1"] is not None:
            rid="REG-"+str(int(tx["addr1"]))
            add(rid,"region",str(int(tx["addr1"])),2,"med"); link(c["tx"],rid,"billing region")
        if tx["device"]:
            add(tx["device"],"device",tx["profile"] or tx["device"],1,"high" if len(device_accounts(conn,tx["device"]))>=3 else "med")
            link(acct,tx["device"],"uses")
            mates=device_accounts(conn,tx["device"])
            for a in mates[:8]:
                add(a,"card",a,2,"high" if has_confirmed_fraud(conn,a) else "med",conn.execute("select count(*) from transactions where account=?",(a,)).fetchone()[0])
                link(tx["device"],a,"used by")
                owner=owner_of(conn,a)
                if owner: add(owner,"customer",owner,3); link(a,owner,"owned by")

    a=scoring.analyze(conn,c)
    for p in a["priors"][:5]:
        h=conn.execute("select account,outcome from cases where id=?",(p["id"],)).fetchone()
        if not h: continue
        add(p["id"],"case",p["id"],3,"high" if h["outcome"]=="Confirmed fraud" else "low")
        link(h["account"],p["id"],"similar case")
        add("OUT:"+p["id"],"outcome",h["outcome"],4,"high" if h["outcome"]=="Confirmed fraud" else "low")
        link(p["id"],"OUT:"+p["id"],"outcome")
    for mid in extra_ids:
        h=conn.execute("select account,outcome from cases where id=?",(mid,)).fetchone()
        if h:
            add(mid,"case",mid,3,"high" if h["outcome"]=="Confirmed fraud" else "low")
            link(h["account"],mid,"analyst selected")
    return {"nodes":sorted(nodes.values(),key=lambda n:(n["depth"],n["id"])),
            "edges":edges}
