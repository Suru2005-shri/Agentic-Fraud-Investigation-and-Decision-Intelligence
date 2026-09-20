"""Risk, similarity and evidence-sufficiency scoring.

All numbers shown in the interface come from these functions and the data in the
database. Weights are documented so they can be tuned or replaced with a trained model.
"""
from datetime import datetime
from math import log

from . import graph


def similarity(c, h, net, ipnet, cat_of) -> float:
    s = 0.0
    if h["account"] in net:
        s += 0.40  # earlier case on an account sharing this case's device
    elif h["account"] in ipnet:
        s += 0.20
    if h["pattern"] == c["pattern"]:
        s += 0.25
    if cat_of(h["merchant_id"]) == cat_of(c["merchant_id"]):
        s += 0.10
    diff = abs(log(max(h["amount"], 1) / max(c["amount"], 1)))
    s += 0.15 * max(0.0, 1 - diff / 2.5)
    return min(s, 0.97)


def _fmt_date(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y")
    except Exception:
        return ""


def rank_priors(conn, c, net: set, ipnet: set, limit: int = 8, accounts_only: set | None = None,
                dev_label: str | None = None) -> list[dict]:
    """Resolved cases most similar to case `c`, best first."""
    rows = conn.execute(
        "select id, account, pattern, amount, merchant_id, outcome, resolved_at, live "
        "from cases where stage='resolved' and id!=?", (c["id"],)).fetchall()
    cat_of = lambda m: graph.merchant_category(conn, m)  # noqa: E731
    net_all = set(net) | {c["account"]}
    out = []
    for h in rows:
        if accounts_only is not None and h["account"] not in accounts_only:
            continue
        sim = similarity(c, h, net_all, ipnet, cat_of)
        if h["account"] in net_all:
            why = f"shares device {dev_label}" if dev_label and h["account"] != c["account"] else "earlier case on this account"
        elif h["account"] in ipnet:
            why = "shares an IP address"
        elif h["pattern"] == c["pattern"]:
            why = "same fraud pattern"
        else:
            why = "similar amount and merchant type"
        out.append({"id": h["id"], "sim": round(sim * 100), "out": h["outcome"], "pat": h["pattern"],
                    "date": _fmt_date(h["resolved_at"]), "why": why, "fresh": bool(h["live"])})
    out.sort(key=lambda p: (-p["sim"], p["id"]))
    return out[:limit]


def analyze(conn, c) -> dict:
    """Collect the facts the agent reasons over for one case."""
    acct = c["account"]
    hist = conn.execute("select amount, merchant from transactions where account=? and is_case=0", (acct,)).fetchall()
    n = len(hist)
    avg = sum(r["amount"] for r in hist) / n if n else 10000.0
    ratio = c["amount"] / max(avg, 1000.0)
    seen = {r["merchant"] for r in hist}
    devs = graph.devices_of(conn, acct)
    mates: list[str] = []
    for d in devs:
        mates += [a for a in graph.device_accounts(conn, d) if a != acct and a not in mates]
    ip_mates: list[str] = []
    for ip in graph.ips_of(conn, acct):
        ip_mates += [a for a in graph.ip_accounts(conn, ip) if a != acct and a not in ip_mates and a not in mates]
    dev = devs[0] if devs else None
    priors = rank_priors(conn, c, set(mates), set(ip_mates), limit=8, dev_label=dev)
    fraud = [p["sim"] for p in priors if p["out"] == "Confirmed fraud"]
    return {
        "avg": avg, "n_hist": n, "ratio": ratio, "first_time": c["merchant_id"] not in seen,
        "risky_merchant": graph.merchant_category(conn, c["merchant_id"]) in graph.RISKY_CATEGORIES,
        "device": dev, "mates": mates, "ip_mates": ip_mates, "priors": priors,
        "best_any": (priors[0]["sim"] / 100) if priors else 0.0,
        "best_fraud": (max(fraud) / 100) if fraud else 0.0,
    }


def parts(a: dict) -> tuple[dict, dict]:
    """Risk points (0-100 scale) and evidence-sufficiency fractions, per source of evidence."""
    risk = {
        "base": 5.0,
        "anomaly": 30.0 * min(a["ratio"] / 10.0, 1.0),
        "device": 22.5 * min(len(a["mates"]), 3) / 3.0,
        "prior": 20.0 * a["best_fraud"],
        "merchant": (8.0 if a["first_time"] else 0.0) + (3.0 if a["risky_merchant"] else 0.0),
    }
    suff = {
        "transaction": 0.22 * min(1.0, a["ratio"] / 5.0),
        "history": 0.10 * min(1.0, a["n_hist"] / 6.0),
        "graph": 0.20 * min(1.0, (len(a["mates"]) + (1 if a["ip_mates"] else 0)) / 3.0),
        "prior": 0.20 * a["best_any"],
        "policy": 0.08,
    }
    return risk, suff


def unc_label(unc: int) -> str:
    return "Low" if unc <= 12 else "Medium" if unc <= 36 else "High"


def triage(conn, c) -> tuple[int, int]:
    """Risk score and evidence sufficiency the agent would reach, used to rank cases before they are opened."""
    a = analyze(conn, c)
    rp, sp = parts(a)
    risk = min(99, round(sum(rp.values())))
    suff = round(min(0.98, sum(sp.values())) * 100)
    if risk < 35:
        suff = max(suff, 88)
    return risk, suff
