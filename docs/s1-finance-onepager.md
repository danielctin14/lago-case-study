# Appendix A: Committed spend + overage, how the money flows

*For Acme AI's Head of Finance. The treatment is **illustrative**, to show which numbers Lago produces. It isn't accounting advice; your policy and auditors decide.*

**Example:** a **$30,000** commitment over 3 months. Usage at list price: $8,000, $12,000, $14,000 = **$34,000**, so the commitment is used up in month 3 with **$4,000 of overage**.

**Shape A: prepaid commitment (invoiced upfront, drawn down by usage)**

| | Invoiced | Recognized | Deferred | Lago source |
|---|---:|---:|---:|---|
| Day 1 | **$30,000** | – | $30,000 | Prepaid-credits top-up invoice |
| Month 1 | $0 | $8,000 | $22,000 | Usage invoice, credits applied −$8,000 |
| Month 2 | $0 | $12,000 | $10,000 | Credits applied −$12,000 |
| Month 3 | **$4,000** | $14,000 | $0 | Credits −$10,000; overage invoiced $4,000 |

If usage stays below $30,000, the unused balance is what's left when the credits expire. Lago gives the exact amount and date; your policy decides the "breakage" treatment.

**Shape B: postpaid minimum commitment (quarterly plan).** In Lago, a minimum commitment is evaluated over the plan's billing period, so a 3-month commitment means a **quarterly** plan. The $8k / $12k / $14k accrue as live usage (recognized monthly as delivered), and **one $34,000 invoice** is issued at quarter end. Usage beat the minimum, so there's no true-up. At $25,000 of usage, that invoice would carry a separate **$5,000 true-up** line. Progressive billing (Premium) can invoice during the quarter if needed.

**Implementation timeline:** design (contract → Lago configuration) → integrate (events into a sandbox) → **parallel run of one full billing cycle**, compared line by line with your current invoicing → go-live. The parallel run sets the pace, deliberately: nobody should switch billing systems on trust.

**What Lago does and doesn't do:** it meters and prices usage, tracks prepaid credits, bills commitments, overage and true-ups as distinct lines, and syncs to accounting systems (e.g. NetSuite, Xero). It does **not** replace your ledger or decide your recognition policy. The revenue recognition module (ASC 606 / IFRS 15) is in **private beta**: we're happy to show it, but its output should be reconciled against your ERP before any statutory close relies on it.
