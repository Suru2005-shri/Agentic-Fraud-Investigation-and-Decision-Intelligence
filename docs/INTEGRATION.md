# Integration guide: replacing the stand-ins

The interface only depends on the JSON shapes returned by `backend/main.py`. Everything behind those routes can change. Nothing below has been run against a real TigerGraph instance, so treat it as a plan, not tested code.

## 1. Data: replace `backend/seed.py`

Load the challenge dataset instead of generating one. The application needs these things:

| Concept | SQLite table today | TigerGraph equivalent |
|---|---|---|
| Customer, Account, Device, IP address, Merchant | `entities(id, type, label, attrs)` | Vertex types |
| Ownership, device use, login from IP | `edges(src, dst, rel)` with `owned by`, `used`, `login from` | Edge types |
| Transactions | `transactions` | Transaction vertices or edge attributes |
| Cases (open and resolved) | `cases` plus `timeline`, `evidence`, `findings`, `activity`, `requests`, `audit` | Keep in a relational store, or model resolved cases as Case vertices |

Keep users, sessions, policies, the audit log and the workflow tables in a normal database. Only the graph needs a graph store.

## 2. Graph: replace the functions in `backend/graph.py`

Every graph query in the application is one of these functions. Reimplement them as GSQL queries called through the TigerGraph MCP server or `pyTigerGraph`, keeping the same inputs and outputs:

- `devices_of(conn, account)`, `ips_of`, `device_accounts(conn, device)`, `ip_accounts`, `owner_of`
- `has_confirmed_fraud(conn, account)`
- `merchant_category(conn, merchant_id)`
- `subgraph(conn, case, extra_ids)`: returns `{nodes: [...], edges: [...]}` up to four hops, treating merchants and IPs as leaf nodes

`scoring.analyze` and `scoring.rank_priors` call these. Graph algorithms (for example community detection to find device rings, or node similarity for prior cases) can replace the hand-written similarity in `scoring.similarity`.

## 3. Retrieval: replace `backend/retrieval.py`

`search(conn, query, pattern, k)` returns policy sections with `score` and `why`. Point it at GraphRAG, or at a vector index plus the typology links stored in the `typology` table. The interface shows `why`, so keep returning a short reason.

## 4. Agent: replace `engine.investigate`

`investigate(conn, case_id, delay)` is the rule-based workflow. A language-model orchestrator can take its place: expose `graph`, `scoring`, `retrieval` and the case-writing helpers in `backend/db.py` as tools, and have the model decide which to call. Keep three things:

1. Write each step to the database as it happens (`db.tl_add`, `db.ev_add`, `db.fnd_add`, `db.set_case`). The interface polls these tables.
2. Keep the sufficiency threshold check in code, not in the prompt.
3. Keep `engine.decide_approval` and the role checks in `main.py`. The approval gate must not depend on the model.

## 5. Evidence channels

`engine.request_evidence` records a request and `POST /api/evidence-requests/{id}/respond` records the answer. To use a real channel, send the link returned by the request (`/customer.html?r=...&t=...`) by SMS or push, or call the step-up provider from `request_evidence` and answer from its callback. Analyst requests are answered by `engine.analyst_reply`; replace it with a queue for a human desk.

## 6. Before real use

Replace the demo users and secret, add HTTPS, rate limiting and password rules, move from SQLite to a server database if several writers are needed, and review consent, retention and data-protection rules for customer contact and personal data.
