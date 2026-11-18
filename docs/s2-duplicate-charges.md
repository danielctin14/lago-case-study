# Section 2: SaaSCo duplicated charges (Tokens, Storage, GB-S, Seats)

> **Bottom line**
> Reproduced on Lago v1.57.0. A plan "sync" job that reads the plan, **appends** the charges from its config (which carry no Lago ids) and writes it back puts every SKU on the plan twice, so every subscription is billed **2×**. Lago accepts this silently, because several charges on one metric is a legitimate feature. Nothing broke in Lago; the automation changed, which fits "it worked, then broke a few days later."
> Fixing the **configuration** is quick once reviewed. **Reconciling affected invoices** takes longer.

## 1. Replicating the setup

One monthly plan with four usage charges: Tokens (sum), Storage (max GB), GB-S (sum), Seats (unique count of `seat_id`, **recurring**). ✅ Seats isn't a fixed charge because per-subscription fixed-charge units return `403 feature_unavailable` on self-hosted open source.

[s2_repro.py](../src/lago_case/s2_repro.py) reproduces it three ways: the realistic **sync-append** job (GET plan → append charges without `id` → PUT), a **direct** `POST /plans` with every metric twice (✅ accepted, no warning), and a **duplicate subscription** (fresh `external_id` per run: same symptom, different cause).

```text
Day 0: plan: 4 charges ['gb_seconds', 'seats', 'storage_gb', 'tokens']
Day N: 'price sync' job runs (GET plan -> append desired charges without ids -> PUT)
       plan: 8 charges ['gb_seconds', 'gb_seconds', 'seats', 'seats', ... 'tokens', 'tokens']
       current usage for sub_saasco_demo_001: total $260.00     <- should be $130.00
```

✅ How `PUT /plans` treats charges (undocumented, so probed): a full list **without** ids replaces them (safe). Existing charges **with** ids plus new ones **without** ids keeps both (**duplicates**). Omitting `charges` leaves them alone. `charges: []` **wipes every charge**.

## 2. Confirming it, and the action plan

**Symptom first:** all four SKUs appear as *separate* lines at once, which points at the plan or the subscriptions. Duplicate events would inflate the quantity on one line, not add a line.

| Hypothesis | Signature in Lago |
|---|---|
| **H1** Non-idempotent plan sync (merge-and-PUT, or retry after a timeout) | Same metric twice; the duplicates' `created_at` = the day it broke |
| **H2** Duplicate subscriptions | 2+ active subscriptions on one plan for one customer |
| **H3** Duplicate events (`transaction_id` regenerated) | Doubled quantity on a single line |
| **H4/H5** Webhook handler running twice; plan overrides | Their logs; `lago_parent_id` on charges |

1. **Contain (first hour):** pause the automation; check which invoices are finalized and when the next billing run is.
2. **Confirm:** run the diagnostic with them; match the duplicates' `created_at` to their deploy logs. Activity logs aren't available on open source (✅ 403).
3. **Review, then fix (same day):** several charges on one metric **can be intentional** (filters, per-model prices). Review filters, overrides, the subscriptions on the plan and the invoice impact with the customer; remove only confirmed duplicates, keeping the originals (`--fix` dry-run → sign-off → `--fix --apply`). ✅ Ingested usage is preserved.
4. **Remediate:** refresh draft invoices; credit notes (or void) for finalized ones; quantify per customer.
5. **Prevent (this week):** build the *full* desired charge list with Lago ids and never merge; keep ids stable; refuse to PUT if a metric appears twice without filters or the list is empty; run the diagnostic before each billing run.

## 3. Troubleshooting script

[s2_diagnose.py](../src/lago_case/s2_diagnose.py) is read-only by default and exits 1 on any finding, so it can run as a guardrail. Six checks: duplicate charges and when they appeared, duplicate subscriptions, dollar impact, affected invoices (draft vs finalized), duplicated events, audit-trail availability. A curl + jq version for the customer's engineer is in [scripts/s2_diagnose_curl.sh](../scripts/s2_diagnose_curl.sh) (⚠️ not executed locally).

```text
[1] Plan 'saasco_standard_s2': 8 charges
    DUPLICATE tokens: original created 20:41:52Z, duplicate created 20:41:53Z   <-- when it broke
[3] sub_saasco_demo_001: billed so far $260.00, expected $130.00, excess $130.00
FINDINGS: duplicate charges for 4 SKUs; over-billed $130.00            exit code 1
$ ... --fix --apply   then re-run:
[1] Plan 'saasco_standard_s2': 4 charges · excess $0.00 · CLEAN          exit code 0
```

## 4. Closing the loop

> **Subject:** Duplicated charges: root cause, fix and next steps
>
> Hi [Name], first, I'm sorry. Double invoices land on your customers and your finance team, and I know this cost you time and some awkward conversations. Thank you for flagging it quickly; your logs made the root cause easy to pin down.
>
> **What happened:** on [date], the new price-sync job started adding the four charges from your config to the plan without Lago's charge IDs, so Lago created them as new charges. Every SKU was billed twice from that day on.
> **Impact:** [N] customers, [N] invoices, **$[X]** (list attached).
> **What we've done:** removed the duplicates, keeping your original charges and all usage, and [refreshed drafts / issued credit notes].
> **What we need by [date]:** update the job to send existing charge IDs (or the full list without merging); keep it paused until then.
> **So it doesn't come back:** the attached check fails if any plan has a SKU twice; run it before each billing run. I'll check your next billing run on **[date]** myself. Happy to help draft the note to your own customers.
>
> Daniel

**Internally:** a help-center article on updating plan charges safely; product feedback (warn on a metric attached twice without filters, a dry-run mode for `PUT /plans`, a confirmation before `charges: []`); an offer to review their other automations.
