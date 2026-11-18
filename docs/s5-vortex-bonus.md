# Bonus: Vortex AI, 90-day renewal and expansion plan

> **Bottom line**
> Vortex's problem is **trust, not missing features**: the CFO calls Lago a burden, the VP Eng wants reliability, and nobody at Lago can explain how the account works today. We earn the renewal by making month-end close boring again, and pitch expansion only once there's measured proof. Each phase ends on measurable exit criteria; owners are in brackets.

**Days 1–30: restore trust, establish facts**
- Lago's CEO replies to the CFO in week 1, naming one accountable owner and this plan [CEO, drafted by SE + AE].
- Joint incident review: a root cause for every recent incident, not just a patch [SE + Lago engineering].
- Map the ERP reconciliation end to end with the external integrator [SE].
- An inventory of what's configured vs the contract and its 3 add-ons, and what's actually used [SE].
- A 1:1 with the quiet FP&A operator before each weekly call [SE].
- Renewal discovery starts now, without pricing: procurement, security/legal, decision-makers, timeline [AE].
- *Exit:* every incident has a root cause, owner and date; the reconciliation runbook is signed off by FP&A and the integrator; a **baseline at close #1** (Lago↔ERP variance, manual adjustments, days to close).

**Days 31–60: prove improvement**
- A daily Lago↔ERP reconciliation report [SE + integrator], the same pattern as my Section 3 `v_customer_billing` view.
- Root-cause fixes shipped [Lago engineering].
- Reliability indicators: ingestion lag, failed syncs, invoice corrections [CSM].
- The FP&A operator presents the numbers in the weekly.
- *Exit:* **close #2** within the agreed variance target, zero repeat incidents, fewer manual adjustments, reported by Finance, not Lago.

**Days 61–90: conditions for renewal and expansion**
- A business review with the CFO and VP Eng: baseline vs now [AE + SE, FP&A presents].
- Validate adoption gaps the 20-person setup never needed [SE].
- Hand the AE an evidence-backed expansion case [SE → AE].
- *Exit:* the CFO confirms close is no longer a blocker; exec sponsors on both sides with a quarterly cadence; a proposal citing measured results.

**Expansion, pitched only after close #2 improves:** evaluate moving from the legacy modular contract to an enterprise package, based on actual usage, adoption, reliability and support needs, and demonstrated value. Candidates: a native accounting integration (if their ERP is supported) to reduce the integrator dependency; a support SLA and named contact; activity/audit logs (unavailable on lower tiers in my Section 2 test, and exactly what root-causing incidents needs); rev-rec (beta) only if Finance asks.

**Top risks:** close #2 doesn't improve → a short bridge renewal with explicit success criteria, not a forced upsell. The integrator blocks visibility → escalate through Vortex's VP Eng. Another incident → root cause within 48h, shared with the CFO before she asks.
