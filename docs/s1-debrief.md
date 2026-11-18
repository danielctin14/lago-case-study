# Section 1A: Acme AI demo debrief (internal)

**To:** [AE], #deal-acme-ai · **From:** Daniel (SE) · sent ~1h after the call

> **Bottom line**
> The VP Eng is engaged, but technical validation and finance buy-in remain open, and we left without a next step.
> The deal moves only if we win the **Staff Engineer** (Kafka) and the **Head of Finance** (rev-rec) in the next 10 days, so the follow-up has to earn **two dated sessions**.

*Assumption (the brief doesn't say): the demo walked through usage events → billable metrics → a committed-spend plan with overage → the invoice.*

## Stakeholders and deal health

| Role | Status | My read | Needs, to say yes |
|---|---|---|---|
| **VP Engineering** (sponsor, champion candidate) | 🟢 fit · 🟠 untested champion | Mapped Lago onto their stack himself | A low-risk plan he can present internally without us |
| **Head of Finance** (approver, likely veto) | 🟠 | Joined for 15 min with two precise questions; my rev-rec answer wasn't crisp | A worked example with numbers, and proof her close doesn't get harder |
| **Staff Engineer** (implementer, quiet veto) | 🟠 | Silent until the last minute; his question is really about effort | A concrete integration pattern and an effort estimate |
| **Momentum** | 🔴 | "We'll be in touch." No date, no owner | Two dated sessions |

## The open questions, answered properly

**Kafka.** **Yes, no custom connector.** 📘 Lago either consumes from **their** topic or they publish to a **Lago-hosted** one (VPC peering or PrivateLink), on Lago's ClickHouse event store, which Lago Cloud manages. The main change on their side is mapping messages to Lago's event fields; we also validate network access, credentials and throughput together. REST batch takes the same schema, so a pilot can start there. ⚠️ Confirm which tier includes streaming ingestion **before** the email goes out.

**Rev-rec.** What I *should* have said:
> "Lago produces your billing numbers: what was invoiced, for which service period, and how much commitment was consumed. Your ERP stays the ledger. Prepaid commitment is deferred and recognized as it's consumed; overage as it's used; unused commitment or a true-up is its own line, so your policy applies cleanly."

📘 Building blocks: wallets, minimum commitments, progressive billing. The rev-rec module is in private beta, worth showing, but her close shouldn't depend on it. Details are in Appendix A.

**Timeline.** The call answer was fine. Appendix A restates it as phases; the one-cycle parallel run sets the pace.

## What I'd do differently
- **Bring late joiners up to speed.** A 60-second recap when Finance joined would have stopped me answering a finance question in billing vocabulary.
- **Never leave on "we'll be in touch."** I set up the next meeting myself and confirm the slot on the call.
- **Every open topic gets an owner and a hard deadline.** "Kafka answer by tomorrow 10:00," not "I'll follow up."
- **Draw quiet people in early.** "How would this sit next to your pipeline?" in minute 10, not minute 59.

## Actions and risks

| # | Action | Owner | Deadline |
|---|---|---|---|
| 1 | Confirm the streaming-ingestion tier and the ClickHouse requirement | Daniel + Lago product | **Today 18:00** |
| 2 | Send the follow-up email with Appendices A and B | Daniel | **Tomorrow 10:00** |
| 3 | Call the VP Eng to lock the sessions (a call converts better than email) | **AE** | **48h** |
| 4 | Line up a Lago finance specialist and a Lago engineer for the sessions | Daniel | **Fri** |
| 5 | Sandbox with their pricing, plus the event mapping from their sample message | Daniel | **Before session** |
| 6 | No slot by Friday: AE nudges the VP; I send the Kafka note to the Staff Engineer directly | AE + Daniel | **Mon** |

**Risks:** the decision happens in the "team sync" without us (→ a forwardable package); a late Finance veto (→ a finance session now); "we'll build it ourselves" (→ map their sample message and size the effort together); a packaging surprise (→ confirm tiers before anything commercial). **Ask to the AE:** own decision process, paper process and competition in your call with the VP.
