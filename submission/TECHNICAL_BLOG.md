# ARGUS — Agentic Fraud Investigation with TigerGraph

## What we built

ARGUS is an agentic fraud-investigation system designed around the HHG benchmark. Instead of treating a bank risk score as a final fraud label, ARGUS investigates the transaction, traverses connected entities, retrieves prior cases, identifies a fraud pattern, evaluates uncertainty, requests additional evidence when needed, and produces a policy-constrained next-best action.

The submission contains:

- a working FastAPI + JavaScript investigation console;
- 20 benchmark case outputs under `submission/cases/`;
- an evidence-request and approval workflow;
- explainable case timelines and reports;
- case-memory retrieval from 5,565 historical cases;
- a TigerGraph schema and full-data export/loading path;
- a compact local graph cache for fast demonstration;
- validation tests.

## Architecture

```text
HHG Dataset
   |
   +--> Transaction + Identity preprocessing
   |
   +--> TigerGraph
   |      Customer -- Card -- Transaction
   |          |          |
   |          |          +-- DeviceProfile
   |          |          +-- BillingRegion
   |          |          +-- EmailDomain
   |          +-- ClosedCase / InvestigationCase
   |
   +--> ARGUS Agent
          |
          +--> Trigger parser
          +--> Graph evidence retrieval
          +--> Transaction-history analysis
          +--> Pattern classifier
          +--> Case-memory retrieval
          +--> Uncertainty / evidence-gap detector
          +--> Controlled evidence request
          +--> Policy engine
          +--> Next-best action
          +--> Human approval gate
          +--> Case closure + memory
          |
          +--> Investigation UI / report
```

## How TigerGraph is used

The graph is the relationship and context layer. A transaction is not investigated in isolation. The agent can move from a Card to its Customer, DeviceProfile, BillingRegion, EmailDomain, connected cards and historical cases. This makes shared-device and repeated-fraud relationships explicit.

The repository provides `tigergraph/schema.gsql`, `tigergraph/load.gsql`, and `tigergraph/export_tigergraph.py`. The loading job follows TigerGraph's GSQL loading-job model: define file variables, load vertices/edges, and run the loading job.

## Agentic workflow

### 1. Trigger

An investigation starts from a fraud risk score, customer report, or analyst request.

### 2. Investigate

ARGUS creates a case and examines transaction history, identity signals, device relationships, billing regions and historical cases.

### 3. Gather evidence

The agent records evidence items with a source and graph/entity references. Evidence is not mixed with unsupported conclusions.

### 4. Assess uncertainty

The agent produces a triage probability and evidence-sufficiency measure. A single weak signal does not automatically become a block decision.

### 5. Request more evidence

The workflow supports customer validation, step-up authentication and analyst information requests. Responses are appended to the same case.

### 6. Update the recommendation

The agent recomputes the recommendation after evidence changes. The case stores both the pre-evidence and post-evidence recommendation.

### 7. Apply policy and permissions

High-impact actions such as blocking a card or escalating an undocumented pattern are routed through the appropriate approval path. The UI prevents an analyst from approving an action reserved for an approver.

### 8. Close and remember

The final outcome, evidence, action and approval are stored as case memory. Future investigations can retrieve those historical outcomes.

## Policy layer

The implementation encodes the challenge policy rules R1–R10. Important controls include:

- verify before blocking on a weak single signal;
- customer denial → block/create case, with reporting for high exposure or shared-origin cases;
- customer confirmation → close as no fraud;
- card-testing sequence → decline and step-up authentication;
- shared origin → monitor connected cards and report when required;
- undocumented coordinated activity → create case, report and escalate;
- never block all cards without the policy conditions being met.

## Dataset handling

The original dataset is not modified. The local demo cache contains the 20 benchmark customers, graph-linked device windows, and the historical case memory required by the interface. The TigerGraph exporter can load the full transaction and identity source into the production graph.

## What we learned

The strongest implementation lesson was that fraud investigation is not only classification. A useful agent must manage evidence state: what is known, what is uncertain, what should be requested next, and which action is allowed under policy.

A second lesson is that graph context changes the investigation. A device profile or card relationship can turn a single suspicious transaction into a broader connected investigation, while prior cases provide outcome-aware memory.

## What we would improve with more time

1. Replace the local graph adapter with direct TigerGraph MCP calls in the production runtime.
2. Add graph-native GSQL queries for reusable fraud motifs and connected-component analysis.
3. Add stronger entity resolution for device and identity signals.
4. Add a calibrated probabilistic model trained only on historical cases and evaluate it with time-based validation.
5. Add immutable evidence hashes and a production audit store.
6. Add more controlled action simulators for bank systems.
7. Add benchmark-level automated regression tests for all 20 cases.

## References

TigerGraph GSQL loading jobs: https://docs.tigergraph.com/gsql-ref/current/ddl-and-loading/creating-a-loading-job

TigerGraph graph schema: https://docs.tigergraph.com/gsql-ref/current/ddl-and-loading/defining-a-graph-schema

Official TigerGraph MCP server: https://github.com/tigergraph/tigergraph-mcp
