# Tonight's handoff

## Already done

- Real HHG case pack wired into ARGUS.
- 5,565 closed historical cases loaded as memory.
- 20 benchmark cases represented.
- Graph relationships for cards, customers, devices and regions implemented.
- Evidence-request workflow implemented.
- Approval workflow and role permissions implemented.
- Policy rules R1–R10 encoded.
- 20 answer JSON files generated.
- SAR decision/narrative included where policy criteria are met.
- TigerGraph schema/loading/export path created.
- 20-case demo graph CSVs included under `tigergraph/demo_data/`.
- Demo SQLite cache included so the app starts immediately.
- `pytest -q` passes 6/6.

## Only manual TigerGraph step

The chat environment cannot log into the private TigerGraph/Savanna account or create a cloud graph on your behalf. Do not send the Gmail password here.

1. Open TigerGraph Savanna.
2. Create a graph named `ARGUS_FRAUD`.
3. Run `tigergraph/schema.gsql`.
4. Upload `tigergraph/demo_data/` as the graph data files.
5. Run `tigergraph/load.gsql`.
6. Verify a benchmark case has Card → DeviceProfile → connected Card → ClosedCase relationships.
7. If using MCP, install `requirements-tigergraph.txt`, configure `tigergraph/.env.example` with your own API token, and start `tigergraph-mcp`.

## Final upload

Use `ARGUS_SUBMISSION_READY.zip`. It intentionally does not include the raw 590k-row challenge dataset; the dataset can remain private/local and the full TigerGraph exporter is included.
