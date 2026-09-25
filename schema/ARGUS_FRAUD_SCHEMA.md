# ARGUS_FRAUD — TigerGraph Schema

## Vertex types

- Customer
- Card
- Transaction
- DeviceProfile
- BillingRegion
- EmailDomain
- ClosedCase
- InvestigationCase

## Important edge types visible in the graph

- CustomerCard — Customer → Card
- CardCustomer — Card → Customer
- CardTransaction — Card → Transaction
- TransactionCard — Transaction → Card
- CardClosedCase — Card → ClosedCase
- CardInvestigationCase — Card → InvestigationCase
- InvestigationDevice — InvestigationCase → DeviceProfile
- InvestigationTransaction — InvestigationCase → Transaction
- Billing/region and email-domain relationships as configured in the graph schema

## CardTransaction verification note

The schema screenshot confirms:

- Edge name: `CardTransaction`
- Direction: Directed
- From: `Card`
- To: `Transaction`

The current test query returned an empty result, so the edge *schema* is confirmed but the actual edge-instance mapping/loading still needs verification. Do not overwrite the graph or recreate the edge until the data mapping is checked.
