"""Export the HHG CSVs into TigerGraph-ready core vertex/edge files.

This does not modify the source dataset and never uses the original public IEEE-CIS file.
"""
import argparse, hashlib
from pathlib import Path
import pandas as pd

TX_COLS=["TransactionID","TransactionAmt","ProductCD","card1","card5","addr1","addr2",
         "P_emaildomain","R_emaildomain","customer_id","ts","channel","risk_score"]
ID_COLS=["TransactionID","id_15","id_23","id_30","id_31","id_33","id_34","DeviceType","DeviceInfo"]

def profile_df(ids):
    z=ids[["DeviceInfo","id_30","id_31","id_33"]].fillna("").astype(str).replace("nan","")
    return z.apply(lambda r:" | ".join(v.strip() for v in r if v.strip()),axis=1).replace("",None)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",required=True,help="Directory containing transactions.csv, identity.csv, case_pack.csv, closed_cases_history.csv")
    ap.add_argument("--out",default="tigergraph/data")
    a=ap.parse_args()
    data=Path(a.data); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    tx=pd.read_csv(data/"transactions.csv",usecols=TX_COLS)
    ids=pd.read_csv(data/"identity.csv",usecols=ID_COLS)
    ids["profile"]=profile_df(ids)
    ids["device"]=ids.profile.map(lambda x: "DEV-"+hashlib.sha1(str(x).encode()).hexdigest()[:12] if x else None)
    df=tx.merge(ids[["TransactionID","profile","device"]],on="TransactionID",how="left")
    df["sig"]=df.customer_id.astype(str)+"|"+df.card1.astype(str)+"|"+df.card5.astype(str)
    cp=pd.read_csv(data/"case_pack.csv"); cc=pd.read_csv(data/"closed_cases_history.csv")
    known={}
    for r in cp.itertuples():
        m=df[df.TransactionID==int(r.flagged_txn_id)].iloc[0]
        known[m.sig]=r.card_id
    for r in cc.itertuples():
        if pd.isna(r.first_fraud_txn_id): continue
        m=df[df.TransactionID==int(r.first_fraud_txn_id)]
        if len(m): known[m.iloc[0].sig]=r.card_id
    for cid,g in df[["customer_id","sig"]].drop_duplicates().groupby("customer_id"):
        used={known[s] for s in g.sig if s in known}; k=1
        for s in sorted(g.sig):
            if s in known: continue
            while f"{cid}-K{k}" in used: k+=1
            known[s]=f"{cid}-K{k}"; used.add(f"{cid}-K{k}"); k+=1
    df["card_id"]=df.sig.map(known).fillna(df.customer_id.astype(str)+"-K1")

    customers=pd.DataFrame({"id":sorted(df.customer_id.dropna().astype(str).unique())})
    cards=df[["card_id","customer_id"]].drop_duplicates().rename(columns={"card_id":"id"})
    transactions=df[["TransactionID","TransactionAmt","ts","ProductCD","channel","risk_score","card1","card5","addr1","addr2","P_emaildomain","R_emaildomain"]].copy()
    transactions.columns=["id","amount","ts","product_cd","channel","risk_score","card1","card5","addr1","addr2","p_emaildomain","r_emaildomain"]
    devices=df[["device","profile"]].dropna(subset=["device"]).drop_duplicates().rename(columns={"device":"id"})
    regions=df[["addr1"]].dropna().drop_duplicates().copy(); regions["id"]="REG-"+regions.addr1.astype(int).astype(str); regions["region_code"]=regions.addr1.astype(int).astype(str); regions=regions[["id","region_code"]]
    domains=set(x for x in pd.concat([df.P_emaildomain,df.R_emaildomain]).dropna().astype(str) if x and x!="nan")
    emails=pd.DataFrame({"id":["EMAIL-"+hashlib.sha1(x.encode()).hexdigest()[:12] for x in sorted(domains)],"domain":sorted(domains)})
    email_id=dict(zip(emails.domain,emails.id))

    closed=pd.DataFrame({
      "id":cc.case_id.astype(str),"pattern":cc.pattern.astype(str),
      "outcome":cc.outcome.map({"confirmed_fraud":"confirmed_fraud","cleared":"cleared"}).astype(str),
      "exposure_usd":cc.exposure_usd.astype(float)})
    inv=pd.DataFrame({"id":cp.case_id.astype(str),"benchmark_no":range(1,len(cp)+1),"pattern":["undetermined"]*len(cp),"status":["new"]*len(cp)})

    customers.to_csv(out/"customers.csv",index=False)
    cards.to_csv(out/"cards.csv",index=False)
    transactions.to_csv(out/"transactions_core.csv",index=False)
    devices.to_csv(out/"devices.csv",index=False)
    regions.to_csv(out/"regions.csv",index=False)
    emails.to_csv(out/"email_domains.csv",index=False)
    closed.to_csv(out/"closed_cases.csv",index=False)
    inv.to_csv(out/"investigation_cases.csv",index=False)

    df[["customer_id","card_id"]].drop_duplicates().rename(columns={"customer_id":"from","card_id":"to"}).to_csv(out/"customer_card.csv",index=False,header=True)
    df[["card_id","TransactionID"]].drop_duplicates().rename(columns={"card_id":"from","TransactionID":"to"}).to_csv(out/"card_transaction.csv",index=False,header=True)
    df[["card_id","device"]].dropna().drop_duplicates().rename(columns={"card_id":"from","device":"to"}).to_csv(out/"card_device.csv",index=False,header=True)
    df[["card_id","addr1"]].dropna().drop_duplicates().assign(to=lambda x:"REG-"+x.addr1.astype(int).astype(str))[["card_id","to"]].rename(columns={"card_id":"from"}).to_csv(out/"card_region.csv",index=False,header=True)
    te=[]
    for col in ("P_emaildomain","R_emaildomain"):
        x=df[["TransactionID",col]].dropna().drop_duplicates()
        x=x[x[col].astype(str)!="nan"].assign(to=x[col].map(email_id))[["TransactionID","to"]].rename(columns={"TransactionID":"from"})
        te.append(x)
    pd.concat(te,ignore_index=True).drop_duplicates().to_csv(out/"transaction_email.csv",index=False)
    cc[["case_id","card_id"]].drop_duplicates().rename(columns={"case_id":"from","card_id":"to"}).to_csv(out/"case_card.csv",index=False)
    # Case-device links are derived from the case's transaction IDs.
    rows=[]
    for r in cc.itertuples():
        for tid in str(r.txn_ids).split("|"):
            if not tid.isdigit(): continue
            m=df[df.TransactionID==int(tid)]
            if len(m) and pd.notna(m.iloc[0].device): rows.append((r.case_id,m.iloc[0].device))
    pd.DataFrame(rows,columns=["from","to"]).drop_duplicates().to_csv(out/"case_device.csv",index=False)
    cp[["case_id","card_id"]].rename(columns={"case_id":"from","card_id":"to"}).to_csv(out/"investigation_card.csv",index=False)
    cp[["case_id","flagged_txn_id"]].rename(columns={"case_id":"from","flagged_txn_id":"to"}).to_csv(out/"investigation_transaction.csv",index=False)
    invdev=[]
    for r in cp.itertuples():
        m=df[df.TransactionID==int(r.flagged_txn_id)]
        if len(m) and pd.notna(m.iloc[0].device): invdev.append((r.case_id,m.iloc[0].device))
    pd.DataFrame(invdev,columns=["from","to"]).drop_duplicates().to_csv(out/"investigation_device.csv",index=False)
    # Initial prior-case links: same customer/card history.
    prior=cc.merge(cp[["card_id"]],on="card_id",how="inner")[["case_id","card_id"]]
    prior=prior.rename(columns={"card_id":"benchmark_card"})
    pairs=[]
    for r in cp.itertuples():
        for x in cc[cc.card_id==r.card_id].case_id.tolist(): pairs.append((r.case_id,x))
    pd.DataFrame(pairs,columns=["from","to"]).drop_duplicates().to_csv(out/"investigation_prior_case.csv",index=False)
    print(f"Exported TigerGraph files to {out}")

if __name__=="__main__": main()
