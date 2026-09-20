"""Hybrid retrieval over policy sections: text similarity (TF-IDF) plus a graph link.

The graph link is pattern -> typology -> policy section. Sections linked to the
case's fraud pattern get a boost, in the spirit of GraphRAG. It is deliberately small
and dependency free so it can be swapped for a real vector index.
"""
import math
import re
from collections import Counter

STOP = set("a an and are as at be by for from in is it of on or that the this to with when where than then".split())


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 1]


def search(conn, query: str, pattern: str | None = None, k: int = 3) -> list[dict]:
    rows = conn.execute("select id, title, text from policies").fetchall()
    docs = [tokens(r["title"] + " " + r["text"]) for r in rows]
    n = len(docs)
    df = Counter(t for d in docs for t in set(d))
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    q = Counter(tokens(query))
    linked, tid = set(), None
    if pattern:
        t = conn.execute("select tid, policy_ids from typology where pattern=?", (pattern,)).fetchone()
        if t:
            tid = t["tid"]
            linked = set(t["policy_ids"].split(","))
    out = []
    qn = math.sqrt(sum((c * idf.get(t, 1)) ** 2 for t, c in q.items())) or 1
    for r, d in zip(rows, docs):
        tf = Counter(d)
        dn = math.sqrt(sum((c * idf[t]) ** 2 for t, c in tf.items())) or 1
        dot = sum(q[t] * idf.get(t, 1) * tf[t] * idf[t] for t in q if t in tf)
        text_score = dot / (qn * dn)
        graph_boost = 0.25 if r["id"] in linked else 0.0
        matched = sorted({t for t in q if t in tf}, key=lambda t: -idf.get(t, 1))[:4]
        why = []
        if graph_boost:
            why.append(f"linked to typology {tid} for {pattern}")
        if matched:
            why.append("matches: " + ", ".join(matched))
        out.append({"id": r["id"], "title": r["title"], "text": r["text"],
                    "score": round(text_score + graph_boost, 3), "why": "; ".join(why) or "weak match",
                    "typology": tid})
    out.sort(key=lambda x: -x["score"])
    return out[:k]
