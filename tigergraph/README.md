# TigerGraph deployment

The challenge requires TigerGraph graph storage/retrieval. The repository keeps a fast SQLite benchmark cache for the demo UI, while this folder provides the full TigerGraph path.

## 1. Fast demo path

The repository already contains `tigergraph/demo_data/`, a 20-benchmark investigation graph cache. You can upload those CSVs first to get the graph running tonight.

## 2. Full-data export



```bash
python tigergraph/export_tigergraph.py --data /path/to/fraud --out tigergraph/data
```

The exporter reads the original `transactions.csv`, `identity.csv`, `case_pack.csv`, and `closed_cases_history.csv`. It creates core vertices/edges without modifying the source files.

## 3. Create the graph

Run `tigergraph/schema.gsql` in GSQL Shell or GraphStudio. It creates `ARGUS_FRAUD`.

## 4. Load

Copy `tigergraph/data/` to the graph's file-accessible data location, then run:

```gsql
USE GRAPH ARGUS_FRAUD
RUN LOADING JOB load_argus
```

If your environment requires runtime file paths, replace the `DEFINE FILENAME` values or use the loading-job runtime arguments supported by your TigerGraph version.

## 5. MCP

TigerGraph's official MCP server supports TigerGraph 4.1+ and pyTigerGraph. Install:

```bash
pip install tigergraph-mcp
```

Create `.env` from `.env.example`, then run:

```bash
tigergraph-mcp
```

The agent can then use graph traversal/query tools through MCP. Keep the API token outside Git.

Official references:
- TigerGraph loading jobs: https://docs.tigergraph.com/gsql-ref/current/ddl-and-loading/creating-a-loading-job
- TigerGraph schema: https://docs.tigergraph.com/gsql-ref/current/ddl-and-loading/defining-a-graph-schema
- Official TigerGraph MCP: https://github.com/tigergraph/tigergraph-mcp
