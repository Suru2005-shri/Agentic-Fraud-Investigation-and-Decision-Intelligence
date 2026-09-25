# ARGUS_FRAUD — Agentic Fraud Investigation on TigerGraph Savanna

> **ARGUS_FRAUD** is a graph-based fraud investigation environment built around **TigerGraph Savanna**. The graph stores customers, cards, transactions, devices, regions, email domains, closed investigations and active investigation cases so that fraud evidence can be explored through relationships instead of isolated transaction rows.

## 1. Project Overview

ARGUS is designed as an **agentic fraud investigation system**.

The investigation flow is:

```text
Fraud / customer / analyst trigger
            ↓
      Investigation Case
            ↓
     Graph evidence retrieval
            ↓
Customer → Card → Transaction
            ↓
Device / Region / Email / Prior Cases
            ↓
Risk + pattern assessment
            ↓
Additional evidence when uncertainty remains
            ↓
Next-best action + approval route
            ↓
Explainable case record
            ↓
Case memory for future investigations
```

TigerGraph Savanna acts as the graph evidence layer. The graph schema is designed so that an investigator/agent can traverse relationships between entities that are difficult to discover in a flat transaction table.

## 2. Main Objectives

1. Represent fraud-investigation entities as a connected graph.
2. Load transaction and supporting entity data into TigerGraph.
3. Connect customers, cards and transactions.
4. Enrich investigations with device, billing-region and email-domain context.
5. Preserve closed investigation history for case memory.
6. Support graph traversal for fraud investigation.
7. Run GSQL queries for high-risk transactions and relationship discovery.
8. Provide evidence that can be consumed by the ARGUS investigation agent.

## Architeture Diagram
docs/architecture.png

## 3. Technology

- TigerGraph Savanna / TigerGraph Cloud
- Graph schema and graph data loading
- GSQL
- Graph traversal
- Graph-based fraud investigation
- Agentic investigation workflow
- GraphRAG-compatible evidence layer
- Optional application/UI layer outside TigerGraph

TigerGraph documentation describes the schema as the model of vertex and edge types, followed by data mapping and loading. The project follows that workflow.

## 4. Graph Name

```text
ARGUS_FRAUD
```

## 5. Graph Schema

### Vertex Types

| Vertex | Purpose |
|---|---|
| `Customer` | Customer/account entity |
| `Card` | Payment card entity |
| `Transaction` | Transaction-level fraud signal and attributes |
| `DeviceProfile` | Device/browser/profile context |
| `BillingRegion` | Billing/address region context |
| `EmailDomain` | Email-domain context |
| `ClosedCase` | Historical investigation/case memory |
| `InvestigationCase` | Current investigation record |

### Important Relationships

| Edge | From | To | Purpose |
|---|---|---|---|
| `CustomerCard` | Customer | Card | Customer owns/uses card |
| `CardCustomer` | Card | Customer | Reverse customer relationship |
| `CardTransaction` | Card | Transaction | Card used for transaction |
| `TransactionCard` | Transaction | Card | Reverse transaction-card relationship |
| `CardClosedCase` | Card | ClosedCase | Historical case linkage |
| `CardInvestigationCase` | Card | InvestigationCase | Active investigation linkage |
| `InvestigationDevice` | InvestigationCase | DeviceProfile | Investigation device evidence |
| `InvestigationTransaction` | InvestigationCase | Transaction | Transaction under investigation |

The exact complete edge list should always be taken from the published TigerGraph schema in the workspace.

## 6. Transaction Data Model

The loaded `transactions_core.csv` mapping contains the following transaction attributes:

| Attribute | Type | Description |
|---|---|---|
| `id` | STRING | Transaction identifier |
| `amount` | DOUBLE | Transaction amount |
| `ts` | STRING | Transaction timestamp |
| `product_cd` | STRING | Product code |
| `channel` | STRING | Transaction channel |
| `risk_score` | DOUBLE | Existing transaction risk score |
| `card1` | STRING | Card identifier field |
| `card5` | STRING | Card-related attribute |
| `addr1` | STRING | Address/region field |
| `addr2` | STRING | Address/region field |
| `P_emaildomain` | STRING | Purchaser email domain |
| `R_emaildomain` | STRING | Recipient email domain |

## 7. Other Mapped Data

### Card

Current Card vertex mapping includes:

```text
id          STRING
customer_id STRING
```

### DeviceProfile

```text
id      STRING
profile STRING
```

### Other source files

The TigerGraph workspace contains mappings for:

```text
cards.csv
customers.csv
transactions_core.csv
devices.csv
regions.csv
email_domains.csv
closed_cases.csv
```

## 8. Loading Evidence

The observed TigerGraph Load Data results include:

| File | Status | Loaded lines | Error lines |
|---|---:|---:|---:|
| `cards.csv` | FINISHED | 463 | 0 |
| `customers.csv` | FINISHED | 430 | 0 |
| `transactions_core.csv` | FINISHED | 27,947 | 0 |
| `devices.csv` | FINISHED | 2,033 | 0 |
| `regions.csv` | FINISHED | 100 | 0 |
| `email_domains.csv` | FINISHED | 91 | 0 |
| `closed_cases.csv` | FINISHED | 9,666 | 0 |

These values document the load screens captured during project development.

## 9. Query Verification

### 9.1 Customer smoke test

```gsql
INTERPRET QUERY () FOR GRAPH ARGUS_FRAUD {
  Result = SELECT c
           FROM Customer:c
           LIMIT 10;

  PRINT Result;
}
```

This query is used to verify that Customer vertices are accessible and that the result is explicitly printed.

### 9.2 High-risk transaction test

```gsql
INTERPRET QUERY () FOR GRAPH ARGUS_FRAUD {
  Result = SELECT t
           FROM Transaction:t
           WHERE t.risk_score >= 0.80
           LIMIT 10;

  PRINT Result;
}
```

This is a basic graph-level risk filter. The threshold is a demonstration/query value, not a production fraud policy.

### 9.3 Card → Transaction connectivity test

```gsql
INTERPRET QUERY () FOR GRAPH ARGUS_FRAUD {
  Result = SELECT t
           FROM Card:c - (CardTransaction) - Transaction:t
           LIMIT 10;

  PRINT Result;
}
```

### Current verification finding

The `CardTransaction` schema has been visually confirmed as:

```text
Card  --CardTransaction-->  Transaction
```

However, the connectivity query currently returns:

```json
{
  "Result": []
}
```

Therefore:

> **The CardTransaction edge definition is present, but its actual edge-instance mapping/loading still needs to be verified.**

The correct next verification is the data mapping for:

```text
transactions_core.csv
        ↓
CardTransaction
        ↓
From: Card
To: Transaction
```

Do not delete, overwrite or recreate the existing edge before checking the mapping.

## 10. Expected CardTransaction Mapping

For the current transaction file structure, the intended relationship is:

```text
transactions_core.csv
        |
        +---- card1 ----> Card.id
        |
        +---- id --------> Transaction.id
```

The screenshot evidence shows that the `CardTransaction` edge is:

```text
From = Card
To   = Transaction
```

The actual mapping should be confirmed in the TigerGraph Load Data / Configure Mapping screen before another load is started.

## 11. Why the Graph Matters

A traditional transaction table can show:

```text
Transaction → amount → timestamp → risk score
```

The graph can instead expose:

```text
Customer
   ↓
Card
   ↓
Transaction
   ↓
DeviceProfile
   ↓
Other cards / cases
```

This makes relationship-based evidence available to the investigation agent.

For example, an investigation can examine whether multiple cards, transactions and historical cases share a device/profile or other graph-connected evidence.

## 12. Agentic Investigation Layer

ARGUS is designed around the following investigation lifecycle:

1. **Trigger** — fraud signal, customer report or analyst request.
2. **Investigate** — create/open a case.
3. **Gather evidence** — retrieve relevant graph relationships and transaction history.
4. **Assess uncertainty** — evaluate whether available evidence is sufficient.
5. **Request additional evidence** — only when necessary.
6. **Recommend/execute next action** — subject to policy and approval.
7. **Explain** — record evidence, reasoning, uncertainty and action.
8. **Update case memory** — store the investigation outcome for future cases.

TigerGraph is the relationship/evidence layer; the agent/UI can orchestrate investigation steps around the graph.

## 13. Repository Structure

```text
ARGUS_FRAUD_TigerGraph_README/
│
├── README.md
│
├── docs/
│   └── screenshots/
│       └── tigergraph_savanna/
│           ├── all captured TigerGraph/Savanna screenshots
│           └── current verification screenshots
│
├── queries/
│   ├── 01_customer_smoke_test.gsql
│   ├── 02_high_risk_transactions.gsql
│   ├── 03_card_transaction_connectivity_test.gsql
│   └── 04_customer_card_transaction_path.gsql
│
└── schema/
    └── ARGUS_FRAUD_SCHEMA.md
```



### Individual Screens

#### 01-login

![01-login](docs/screenshots/argus_website/01-login.jpg)

#### 02-command-center

![02-command-center](docs/screenshots/argus_website/02-command-center.jpg)

#### 03-investigating-live

![03-investigating-live](docs/screenshots/argus_website/03-investigating-live.jpg)

#### 04-evidence-gap

![04-evidence-gap](docs/screenshots/argus_website/04-evidence-gap.jpg)

#### 05-customer-validation

![05-customer-validation](docs/screenshots/argus_website/05-customer-validation.jpg)

#### 06-customer-link-page

![06-customer-link-page](docs/screenshots/argus_website/06-customer-link-page.jpg)

#### 08-after-evidence

![08-after-evidence](docs/screenshots/argus_website/08-after-evidence.jpg)

#### 09-approval

![09-approval](docs/screenshots/argus_website/09-approval.jpg)

#### 10-resolved

![10-resolved](docs/screenshots/argus_website/10-resolved.jpg)

#### 11-report-with-audit-trail

![11-report-with-audit-trail](docs/screenshots/argus_website/11-report-with-audit-trail.jpg)

#### 12-case-memory

![12-case-memory](docs/screenshots/argus_website/12-case-memory.jpg)

#### 13-memory-in-graph

![13-memory-in-graph](docs/screenshots/argus_website/13-memory-in-graph.jpg)

#### 14-policy

![14-policy](docs/screenshots/argus_website/14-policy.jpg)

#### 15-benchmark

![15-benchmark](docs/screenshots/argus_website/15-benchmark.jpg)

## 16. How to Reproduce the TigerGraph Setup

1. Open TigerGraph Savanna / TigerGraph Cloud.
2. Open the workspace containing `ARGUS_FRAUD`.
3. Open **Design Schema**.
4. Confirm the vertex and edge types.
5. Open **Load Data / Map Data To Graph**.
6. Confirm the CSV files.
7. Confirm each vertex mapping.
8. Confirm edge mappings, especially `CardTransaction`.
9. Publish the data mapping.
10. Load the data.
11. Open **Explore Graph** to verify vertex instances.
12. Open **Query Editor**.
13. Run the Customer smoke test.
14. Run the high-risk transaction test.
15. Run the Card → Transaction connectivity test.
16. Verify JSON output and graph visualization.

## 17. Important Safety / Data Notes

- Do not commit credentials, API keys, database passwords or TigerGraph access tokens.
- Do not include private customer PII in a public repository.
- Use anonymized/hash identifiers where possible.
- Do not overwrite an existing graph merely to fix an edge query.
- Verify schema, mapping and load status before modifying the graph.

## 18. Troubleshooting

### Query returns `results: []`

Check:

1. The query has a `PRINT Result;` statement.
2. The vertex type actually contains data.
3. The edge direction matches the schema.
4. The edge mapping exists.
5. The source and target IDs in the CSV match existing vertex IDs.
6. The edge data was actually loaded.
7. The mapping was published before loading.

### Customer query works but Card → Transaction is empty

This is the current known verification case.

Check:

```text
transactions_core.csv
       ↓
CardTransaction mapping
       ↓
From: Card / card1
To: Transaction / id
       ↓
Publish mapping
       ↓
Load data
```

## 19. What Is Already Verified

- `ARGUS_FRAUD` graph exists.
- Customer vertices are visible in Explore Graph.
- Transaction data is loaded.
- CardTransaction edge schema exists.
- CardTransaction direction is Card → Transaction.
- Query Editor executes GSQL successfully.
- `PRINT Result;` is required to display the query result.
- Load Data screens show successful file loads for the listed source files.

## 20. Remaining Verification Item

Before calling the TigerGraph graph integration fully verified:

**Verify and, if necessary, load the `CardTransaction` edge mapping.**

This is intentionally documented as an open verification item rather than falsely marking the relationship as working.

## 21. Reference Documentation

- TigerGraph Design Schema documentation
- TigerGraph Map Data To Graph documentation
- TigerGraph Load Data documentation
- TigerGraph GSQL documentation

Official documentation:
- https://docs.tigergraph.com/
- https://docs.tigergraph.com/tigergraph-server/current/ddl-and-loading/defining-a-graph-schema
- https://docs.tigergraph.com/gui/current/graphstudio/map-data-to-graph

## 22. Project Status

**Graph foundation:** Ready  
**Vertex data:** Loaded/verified  
**Query execution:** Verified  
**High-risk transaction query:** Prepared  
**CardTransaction schema:** Verified  
**CardTransaction edge instances:** **Mapping/load verification pending**  
**Agentic investigation layer:** Designed around the graph evidence model

---

### ARGUS_FRAUD

**Agentic Fraud Investigation using TigerGraph Savanna**

> From an uncertain fraud signal to connected evidence, explainable investigation and case memory.

```

The website screenshots are kept as the original captured project UI images; no artificial replacement screenshots are used.
