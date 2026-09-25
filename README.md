# ARGUS — Agentic Fraud Investigation & Next-Best Action

ARGUS is the HHG TigerGraph fraud-investigation submission. It turns an uncertain fraud signal into an evidence-backed, policy-controlled investigation.

## Quick start

The repository includes a compact 20-case benchmark cache at `data/argus.db`, so the UI can start without waiting for the 590k-row source dataset to load.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000`.

Demo users:

- Analyst: `analyst` / `analyst123`
- Approver: `approver` / `approver123`
- Admin: `admin` / `admin123`

For a fresh dataset rebuild, set `ARGUS_DATA_DIR` to the extracted challenge dataset or put `fraud.zip` at `data/fraud.zip`, then use the admin reset endpoint.

## Challenge dataset

Expected files:

- `transactions.csv`
- `identity.csv`
- `case_pack.csv`
- `closed_cases_history.csv`

The full TigerGraph path is under `tigergraph/`.

```bash
python tigergraph/export_tigergraph.py --data /path/to/fraud --out tigergraph/data
```

Then create/load `ARGUS_FRAUD` using `tigergraph/schema.gsql` and `tigergraph/load.gsql`.

## Agent workflow

Trigger → investigate → graph evidence → prior-case memory → pattern assessment → uncertainty → additional evidence → next-best action → approval → action → case memory.

Supported evidence requests:

- customer validation;
- step-up authentication;
- analyst information.

Supported action concepts include allow/monitor, verify, step-up, decline, block, create case, report, escalate and connected-card monitoring. High-impact actions are approval-gated.

## Submission

See `submission/` for the 20 benchmark answer files, benchmark summary, demo script, technical blog and social post.

## Tests

```bash
pytest -q
```

## TigerGraph / MCP

The repository contains a TigerGraph 4.x schema/loading path and an MCP configuration guide. The official TigerGraph MCP server is documented in `tigergraph/README.md`.
