# Submission checklist mapped to the challenge

| Requirement / judging area | Where it is implemented |
|---|---|
| Working agent | `backend/main.py`, `backend/engine.py`, `backend/scoring.py` |
| GitHub repository | This project root |
| 20 benchmark answers | `submission/cases/HHG-001.json` … `HHG-020.json` |
| Internal investigation record | Each JSON + case timeline/evidence tables |
| Evidence before/after requested evidence | `next_best_actions.initial` and `.final` + `evidence_requests` |
| Case written to graph | `engine._write_case_memory()` + TigerGraph graph design |
| Suspicious activity report | `sar` object in each answer file; narrative is 6–12 sentences |
| Next-best action | Policy-controlled actions with route: auto / L1 / L2 |
| Additional evidence | Customer / step-up / analyst evidence endpoints |
| Prior cases as memory | `closed_cases_history.csv` → `cases` + graph links |
| Explainability | evidence source/ref/entity IDs, findings, timeline, report endpoint |
| TigerGraph | `tigergraph/schema.gsql`, `load.gsql`, exporter and MCP guide |
| Graph algorithms / traversal | device, card, customer, region and case relationships in graph adapter |
| Agent controls | approval gate + role permissions + evidence request controls |
| Demo | `submission/DEMO_SCRIPT.md` |
| Technical blog | `submission/TECHNICAL_BLOG.md` |
| Social post | `submission/SOCIAL_POST.md` |
| Automated checks | `pytest -q` — 6 tests pass |
