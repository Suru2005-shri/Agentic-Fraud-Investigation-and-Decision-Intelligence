# 3–5 Minute Demo Script — ARGUS

## 0:00–0:25 — Trigger
Open **HHG-006**. Show the customer report, transaction amount, benchmark risk score, and the graph context.

Say: “ARGUS starts from an uncertain fraud signal and does not treat the risk score as the final answer. It creates an investigation record and gathers graph evidence.”

## 0:25–1:20 — Investigation
Click **Investigate** and show the timeline progressing through:
- trigger received
- transaction history analysed
- graph relationships discovered
- prior case memory retrieved
- pattern assessment

Point at the graph and show the flagged card → device profile → connected cards → prior cases.

Say: “The graph gives the agent relationships that are difficult to see in a flat transaction table. The same device profile is connected to multiple cards, and the memory layer retrieves earlier investigations.”

## 1:20–2:00 — Next-best action
Show the recommendation and policy panel.

Say: “ARGUS separates evidence from the decision. The case is classified as card-not-present activity on a new device. The policy layer determines whether to verify, monitor, block, report, or escalate.”

For a customer-report case, show **Block Card** as an approval-gated action.

## 2:00–2:45 — Uncertain case / evidence loop
Open **HHG-005** in a fresh demo database or reset environment. Investigate it until the case asks for customer validation.

Request customer validation. Use the public evidence link and simulate a denial.

Say: “This is the key agentic loop: the recommendation changes after new evidence arrives. The case records what was requested, what came back, and why the recommendation changed.”

## 2:45–3:25 — Analyst route
Open **HHG-014**. Show the analyst-request trigger, analyst evidence request, and connected-device evidence.

Say: “When the signal is an undocumented coordinated pattern, the agent routes the evidence request to an analyst instead of inventing certainty.”

## 3:25–4:00 — Case memory + explainability
Open a resolved case and then return to the benchmark case. Show prior-case links and the case report.

Say: “Every decision leaves a case record. The outcome becomes memory that can inform later investigations.”

## 4:00–4:30 — TigerGraph / architecture
Show the architecture slide or TigerGraph schema.

Say: “The production graph is TigerGraph. Customer, Card, Transaction, DeviceProfile, BillingRegion, EmailDomain and Case are vertices. Relationships such as owns, used-by, billed-in, affected-transaction and prior-case make graph traversal the evidence layer. The local UI includes a compact SQLite cache for a fast demo; the repository also contains the full TigerGraph export and GSQL loading path.”

## Closing line
“ARGUS moves from uncertain fraud signal to a defensible next-best action, while preserving evidence, approvals, explanations and case memory.”
