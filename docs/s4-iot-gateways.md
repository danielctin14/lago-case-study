# Section 4: Usage-based pricing for a connected-gateway vendor

> **Bottom line**
> Most of this is native Lago: a yearly calendar plan paid in advance, graduated tiers, a live gateway count from commissioning/decommissioning events, monthly VPN billing on a yearly plan, current and projected usage for their portal, and invoices handed to the ERP instead of emailed.
> **Not native:** amounts that depend on a **point-in-time snapshot of another metric** (N on 1 January; gateways active on the 1st of each month), and a trial that also covers **charges**.
> Both close with **one small scheduled job** (yearly + monthly) on Premium. Given their "no custom logic on our side" constraint, I'd propose a **Lago-managed implementation, subject to Solutions/product approval**. That's custom work, not configuration.

| # | Question | Verdict | Custom part |
|---|---|---|---|
| 1 | **Gateway base**, per customer, refreshed at renewal | **Configuration + custom** | A yearly job sets N at the 1 January cut-off |
| 2 | **VPN allowance** = gateways on the 1st × GB/gateway | **Custom** | The same job, monthly |
| 3 | **90-day trial** for base and VPN, prorated first invoice | **Partly native** | Start the subscription at trial end; the job prorates the first-year base |

**Native configuration (evidence):**
- **Gateway fleet:** unique count of `gateway_id`, **recurring**, with decommissioning as `operation_type: remove`. ✅ count · 📘 remove
- **VPN:** sum of `gb`, one event per session at session end, so it counts in the month it ends. ✅
- **Plan:** yearly, calendar billing, paid in advance, with `bill_charges_monthly`. ✅ accepted on open source
- **Pricing:** graduated tiers 1 / 2–10 / … / 500+ ✅, and gateways added during the year prorated in arrears. ✅ 12 gateways for 13 of 30 days billed exactly 13/30.
- **Portal and ERP:** current and projected usage for the portal; invoices finalized but not emailed (off by default). 📘

## 1. Gateway base: configuration + custom

Native: graduated tiers, calendar yearly billing in advance, a live count. If amounts differ only because **N** differs, one plan serves every customer.

Not native: "take a snapshot of the count on 1 January, bill it in advance, bill only gateways above it in arrears, never credit below it." A Lago charge bills either the live count or a fixed quantity someone has to set.

**Design:** the **base** is a graduated, in-advance fixed charge with `units = N`. **Additions** are a prorated, in-arrears charge on the gateway count with the first N free. **No credit below N** comes for free, because the base units don't change during the year. ✅ Setting units or overrides per subscription is Premium (`403` on open source).

**The renewal job runs at the contractual cut-off**, not before it:
1. It waits an agreed window for late events stamped before the cut-off.
2. It **reconstructs** N by replaying each subscription's timestamped commissioning/decommissioning events up to the cut-off. It never reads `current_usage`, which describes the open period, not a point in time: a gateway added at 00:15 on 1 January would inflate N.
3. It sets the units and the threshold.
4. Only then is the renewal invoice finalized.

**Safeguards:** a stated timezone for the cut-off; retry-safe "set, never increment" updates; alerts if any subscription is unconfirmed or N jumps beyond a sanity threshold; invoices held in draft until confirmed. ⚠️ Whether a grace period can hold an *advance-billed* fixed charge still needs testing; it's the riskiest assumption here.

## 2. VPN allowance: custom

Native: monthly evaluation, sessions counted in the month they end, per-GB pricing above a free allowance. Not native: an allowance that depends on another metric. Free units are static per charge ✅, and 📘 SQL expressions can't reference another metric.

**Configuration-only alternative, only if they change the offer:** group the VPN charge by `gateway_id` with a per-gateway free allowance. ✅ Tested at 10 GB per gateway with usage of 15 / 15 / 2 GB: the pooled spec bills **$10** (2 GB over 30), while per-gateway bills **$50** (5 + 5 + 0), because a quiet gateway's allowance can't cover a busy one. That's a different promise, so it's their call.

**Recommended:** the same job at each month's cut-off, with the same replay and safeguards, setting the free units per subscription to `count × GB per gateway` (Premium). Unused allowance is lost because the next run overwrites it.

## 3. Trial: partly native

✅ `trial_period: 90` waived a $1,200 in-advance base fee (no invoice at start). But the trial **doesn't cover charges**: ✅ the gateway charge accrued $463.67 during the trial (📘 the same for fixed charges). And 📘 graduated in-advance fixed charges can't be prorated.

**Recommended:**
1. Start the Lago subscription at **trial end** (`subscription_at` = registration + 90 days), on calendar billing.
2. The yearly job applies a one-off credit to prorate the first-year base.
3. ⚠️ To evaluate: Lago's free-plan → paid-plan transition, as an alternative to the delayed start.
4. ⚠️ Events stamped before a subscription starts aren't billed (✅), so the gateway state at trial end must be re-established. That needs a proper test.

## What I'd tell the customer

> "Most of your model is standard Lago configuration: the yearly calendar plan, graduated tiers, proration for added gateways, monthly VPN billing, and live usage for your portal, with invoices flowing to your ERP. Two parts need logic Lago doesn't have natively: N taken as a snapshot on 1 January, and a VPN allowance that follows the gateways active on the 1st. The trial also needs an adjustment, because Lago's trial waives only the base fee. I'd propose a small scheduled job that **we** build and operate, so you still only send raw events. It isn't a standard product feature, so I'll confirm with our Solutions and product teams that we can commit to it, and the effort, before we agree dates. It needs our Premium plan."

**Product feedback:** "units from a point-in-time metric snapshot" and "free units derived from another metric" would make this case native, and both are reusable for any fleet- or seat-based customer.
