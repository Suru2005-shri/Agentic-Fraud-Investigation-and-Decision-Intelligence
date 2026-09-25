"""Evidence-driven scoring for the HHG benchmark.

The score is a triage estimate, not a ground-truth label. The agent uses independent
signals from transaction history, identity data, graph relationships and closed cases.
"""
from datetime import datetime, timedelta
from math import exp, log
from . import graph

def _dt(v): return datetime.fromisoformat(str(v))

def _profile_shared(conn,profile,account,when):
    if not profile: return []
    start=(when-timedelta(days=7)).isoformat(sep=" ")
    end=(when+timedelta(days=7)).isoformat(sep=" ")
    return graph.shared_profiles(conn,profile,account,start,end)

def _card_testing(rows,when):
    # Three or more sub-$5 online authorizations inside one hour, followed by >$100.
    rows=sorted(rows,key=lambda r:r["ts"])
    for i,r in enumerate(rows):
        if r["channel"]!="online" or r["amount"]>=5: continue
        st=_dt(r["ts"]); small=[x for x in rows[i:] if x["channel"]=="online" and x["amount"]<5 and _dt(x["ts"])<=st+timedelta(hours=1)]
        if len(small)>=3:
            large=[x for x in rows if _dt(x["ts"])>_dt(small[-1]["ts"]) and _dt(x["ts"])<=_dt(small[-1]["ts"])+timedelta(hours=2) and x["amount"]>100]
            if large: return True,small,large
    return False,[],[]

def rank_priors(conn,c,net=None,ipnet=None,limit=8,accounts_only=None,dev_label=None):
    """Rank closed case memory using graph-linked device/case relationships plus amount."""
    rows=conn.execute("""select id,account,pattern,amount,merchant_id,outcome,resolved_at,live
                         from cases where stage='resolved' and id!=?""",(c["id"],)).fetchall()
    tx=conn.execute("select profile,device,addr1 from transactions where id=?",(c["tx"],)).fetchone()
    profile=tx["profile"] if tx else None
    device=tx["device"] if tx else None
    device_cases=set()
    if device:
        device_cases={r[0] for r in conn.execute(
            "select src from edges where dst=? and rel='case used device'",(device,)).fetchall()}
    out=[]
    for h in rows:
        if accounts_only is not None and h["account"] not in accounts_only: continue
        score=0.12; why=[]
        if h["account"]==c["account"]:
            score+=0.55; why.append("same card")
        if h["id"] in device_cases:
            score+=0.25; why.append("shared device profile")
        diff=abs(log(max(float(h["amount"] or 1),1)/max(float(c["amount"] or 1),1)))
        score+=0.10*max(0.0,1-diff/2.5)
        if h["pattern"]==c["pattern"] and c["pattern"]!="undetermined":
            score+=0.10; why.append("same pattern")
        if not why: why.append("similar amount")
        out.append({"id":h["id"],"sim":round(min(.97,score)*100),"out":h["outcome"],
                    "pat":h["pattern"],"date":str(h["resolved_at"])[:10],
                    "why":"; ".join(why),"fresh":bool(h["live"])})
    out.sort(key=lambda x:(-x["sim"],x["id"]))
    return out[:limit]


def infer_pattern(conn,c,a):
    if "analyst request" in str(c["trigger"]).lower() and a["shared_accounts"]:
        return "undocumented"
    if a["card_testing"]: return "card_testing"
    if a["out_region"]: return "out_of_region_use"
    if a["new_device"] and a["online"] and (a["burst_count"]>=2 or a["same_fraud"]>=1):
        return "card_not_present_new_device"
    if a["mixed_channel"] and a["new_device"] and a["online"]:
        return "account_takeover"
    if a["online"]:
        return "card_not_present_fraud"
    # Repeated disputed card-present activity that does not match the region pattern.
    if a["customer_report"] and a["same_fraud"]>=2:
        return "undocumented"
    return "none"

def analyze(conn,c):
    acct=c["account"]; t=_dt(c["opened_at"])
    tx=conn.execute("select * from transactions where id=?",(c["tx"],)).fetchone()
    if not tx:
        return {"pattern":"none","probability":0.1,"priors":[],"mates":[],"shared_accounts":[]}
    hist=conn.execute("select * from transactions where account=? and ts<? order by ts",(acct,c["opened_at"])).fetchall()
    recent=conn.execute("select * from transactions where account=? and ts>=? and ts<=? order by ts",
                        (acct,(t-timedelta(days=14)).isoformat(sep=" "), (t+timedelta(hours=1)).isoformat(sep=" "))).fetchall()
    w48=[r for r in recent if t-timedelta(hours=48)<=_dt(r["ts"])<=t]
    online=[r for r in w48 if r["channel"]=="online"]
    new_device=str(tx["id_15"] or "").lower()=="new"
    profile=tx["profile"]
    shared=_profile_shared(conn,profile,acct,t)
    shared_accounts=sorted({r["account"] for r in shared})
    strong_shared=bool(profile and 0<len(shared_accounts)<=10)
    prior=rank_priors(conn,c,limit=8)
    same=conn.execute("select count(*) n,sum(case when outcome='Confirmed fraud' then 1 else 0 end) f from cases where account=? and stage='resolved'",(acct,)).fetchone()
    same_n=int(same["n"] or 0); same_f=int(same["f"] or 0)
    avg=sum(float(r["amount"]) for r in hist)/len(hist) if hist else float(tx["amount"])
    ratio=float(tx["amount"])/max(avg,1)
    regions=[r["addr1"] for r in hist if r["channel"]=="in_person" and r["addr1"] is not None]
    region_counts={}
    for x in regions: region_counts[x]=region_counts.get(x,0)+1
    out_region=(tx["channel"]=="in_person" and tx["addr1"] is not None and
                len(regions)>=5 and tx["addr1"] not in region_counts)
    cardtest,small,large=_card_testing(w48,t)
    mixed=bool({r["channel"] for r in w48}=={"online","in_person"}) or (
        sum(r["channel"]=="online" for r in recent)>0 and sum(r["channel"]=="in_person" for r in recent)>0)
    customer_report="customer" in str(c["trigger"]).lower() or "never made" in str(c["trigger"]).lower()
    burst_count=len(online)
    # Independent evidence -> calibrated probability, deliberately separated from risk_score.
    p=.10
    p += .24*float(tx["risk_score"] or 0)
    if new_device: p+=.10
    if customer_report: p+=.48
    if same_n: p+=.18*(same_f/max(same_n,1))
    if strong_shared: p+=.12
    if cardtest: p+=.18
    if burst_count>=2: p+=.08
    if burst_count>=5: p+=.08
    if out_region: p+=.16
    if mixed: p+=.06
    if ratio>=3: p+=.05
    p=max(.03,min(.98,p))
    a={
      "avg":avg,"ratio":ratio,"hist_count":len(hist),"recent":recent,"w48":w48,"online":online,
      "new_device":new_device,"profile":profile,"shared":shared,"shared_accounts":shared_accounts,
      "strong_shared":strong_shared,"same_n":same_n,"same_fraud":same_f,"priors":prior,
      "burst_count":burst_count,"mixed_channel":mixed,"customer_report":customer_report,
      "out_region":out_region,"card_testing":cardtest,"small_testing":small,"large_after_testing":large,
      "probability":p,"pattern":"none","current":tx
    }
    a["pattern"]=infer_pattern(conn,c,a)
    return a

def parts(a):
    # UI meters: independent evidence coverage, not a probability.
    suff=0.12
    if a["hist_count"]>=10: suff+=.12
    elif a["hist_count"]>=3: suff+=.07
    if a["same_fraud"]: suff+=min(.18,.06*a["same_fraud"])
    if a["profile"]: suff+=.10
    if a["strong_shared"]: suff+=.12
    if a["burst_count"]>=2: suff+=.12
    if a["card_testing"]: suff+=.16
    if a["out_region"]: suff+=.12
    if a["new_device"]: suff+=.08
    if a["customer_report"]: suff+=.18
    suff=min(.98,suff)
    conf=round(suff*100)
    risk=round(a["probability"]*99)
    return {"risk":risk,"confidence":conf,"uncertainty":100-conf,"suff":conf}

def triage(conn,c):
    a=analyze(conn,c); p=parts(a)
    return p["risk"],p["suff"]

def unc_label(unc):
    return "Low" if unc<=12 else "Medium" if unc<=36 else "High"
