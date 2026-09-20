"""Graph access layer.

SQLite tables (entities, edges) stand in for the graph store here. Every function that
touches the graph lives in this module, so a TigerGraph adapter only has to replace
these functions (see docs/INTEGRATION.md).
"""
RISKY_CATEGORIES = {"gift cards", "forex", "prepaid", "gaming"}
_cat_cache: dict[str, str] = {}


def clear_cache() -> None:
    _cat_cache.clear()


def merchant_category(conn, merchant_id: str) -> str:
    if merchant_id not in _cat_cache:
        r = conn.execute("select attrs from entities where id=?", (merchant_id,)).fetchone()
        import json
        _cat_cache[merchant_id] = (json.loads(r["attrs"]).get("category", "other") if r else "other")
    return _cat_cache[merchant_id]


def _col(conn, sql: str, arg: str) -> list[str]:
    return [r[0] for r in conn.execute(sql, (arg,)).fetchall()]


def devices_of(conn, acct: str) -> list[str]:
    return _col(conn, "select dst from edges where src=? and rel='used'", acct)


def ips_of(conn, acct: str) -> list[str]:
    return _col(conn, "select dst from edges where src=? and rel='login from'", acct)


def device_accounts(conn, dev: str) -> list[str]:
    return _col(conn, "select src from edges where dst=? and rel='used'", dev)


def ip_accounts(conn, ip: str) -> list[str]:
    return _col(conn, "select src from edges where dst=? and rel='login from'", ip)


def owner_of(conn, acct: str) -> str | None:
    r = _col(conn, "select dst from edges where src=? and rel='owned by'", acct)
    return r[0] if r else None


def has_confirmed_fraud(conn, acct: str) -> bool:
    return conn.execute("select 1 from cases where account=? and stage='resolved' and outcome='Confirmed fraud' limit 1",
                        (acct,)).fetchone() is not None


def subgraph(conn, c, extra_ids=()):
    """Neighbourhood of the case account, up to four hops, with hubs treated as leaves."""
    from . import scoring
    acct = c["account"]
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def cnt(col, val):
        return conn.execute(f"select count(*) from transactions where {col}=?", (val,)).fetchone()[0]

    def add(nid, typ, label, depth, risk="low", tx=0):
        if nid not in nodes:
            nodes[nid] = {"id": nid, "type": typ, "label": label, "depth": depth, "risk": risk, "tx": tx}

    def link(a, b, label):
        if a in nodes and b in nodes and a != b and not any(e["a"] == a and e["b"] == b for e in edges):
            edges.append({"a": a, "b": b, "label": label})

    devs, ips = devices_of(conn, acct), ips_of(conn, acct)
    add(acct, "account", acct, 0, "high" if (c["risk"] or 0) >= 75 else "med", cnt("account", acct))
    cu = owner_of(conn, acct)
    if cu:
        add(cu, "customer", cu, 1)
        link(acct, cu, "owned by")
    add(c["tx"], "tx", c["tx"], 1, "high" if (c["risk"] or 0) >= 55 or c["stage"] == "new" else "med", 1)
    link(acct, c["tx"], "sent")
    cat = merchant_category(conn, c["merchant_id"])
    add(c["merchant_id"], "merchant", c["merchant"], 2, "med" if cat in RISKY_CATEGORIES else "low",
        cnt("merchant", c["merchant_id"]))
    link(c["tx"], c["merchant_id"], "paid to")
    for d in devs:
        mates = [a for a in device_accounts(conn, d) if a != acct]
        add(d, "device", d, 1, "high" if len(mates) >= 3 else "med" if len(mates) == 2 else "low", cnt("device", d))
        link(acct, d, "used")
    for ip in ips:
        mates = [a for a in ip_accounts(conn, ip) if a != acct]
        add(ip, "ip", ip[3:], 1, "med" if mates else "low", cnt("ip", ip))
        link(acct, ip, "login from")

    mate_rows: list[tuple[str, str, str]] = []
    for d in devs:
        for a in sorted(device_accounts(conn, d)):
            if a != acct and len(mate_rows) < 4:
                mate_rows.append((a, d, "used by"))
    seen = {m[0] for m in mate_rows}
    for ip in ips:
        for a in sorted(ip_accounts(conn, ip)):
            if a != acct and a not in seen and len(mate_rows) < 6:
                mate_rows.append((a, ip, "shared with"))
                seen.add(a)
    for a, via, lbl in mate_rows:
        add(a, "account", a, 2, "high" if has_confirmed_fraud(conn, a) else "med", cnt("account", a))
        link(via, a, lbl)
    for ip in ips:
        for a in ip_accounts(conn, ip):
            if a in nodes and a != acct:
                link(ip, a, "shared with")
    for a, _, _ in mate_rows[:2]:
        o = owner_of(conn, a)
        if o:
            add(o, "customer", o, 3)
            link(a, o, "owned by")

    # earlier cases recorded against the linked accounts
    net = {a for a, _, _ in mate_rows}
    priors = scoring.rank_priors(conn, c, set(net), set(), limit=200, accounts_only=net | {acct})
    for p in priors[:3]:
        h = conn.execute("select account, outcome from cases where id=?", (p["id"],)).fetchone()
        risk = "high" if h["outcome"] == "Confirmed fraud" else "low"
        parent_depth = nodes[h["account"]]["depth"] if h["account"] in nodes else 1
        add(p["id"], "case", p["id"], parent_depth + 1, risk)
        link(h["account"], p["id"], "subject of")
        add("OUT:" + p["id"], "case", h["outcome"], parent_depth + 2, risk)
        link(p["id"], "OUT:" + p["id"], "outcome")

    # cases the analyst pulled in from case memory
    for mid in extra_ids:
        if mid in nodes:
            continue
        h = conn.execute("select account, outcome from cases where id=?", (mid,)).fetchone()
        if not h:
            continue
        risk = "high" if h["outcome"] == "Confirmed fraud" else "low"
        if h["account"] in nodes:
            add(mid, "case", mid, nodes[h["account"]]["depth"] + 1, risk)
            link(h["account"], mid, "subject of")
        else:
            add(mid, "case", mid, 2, risk)
            link(acct, mid, "similar case")
        d = nodes[mid]["depth"]
        add("OUT:" + mid, "case", h["outcome"], d + 1, risk)
        link(mid, "OUT:" + mid, "outcome")

    order = sorted(nodes.values(), key=lambda n: (n["depth"], n["id"]))
    return {"nodes": order, "edges": edges}
