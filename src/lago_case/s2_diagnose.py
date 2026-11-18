"""Section 2: diagnose duplicated charges for a customer (read-only unless --fix --apply).

Checks, in the order I'd run them on a call with the customer:
  1. Duplicate charges on the plan  (same metric + same filters attached more than once)
     -> and WHEN each duplicate was created (charge.created_at), to match against deploys/job runs
  2. Duplicate subscriptions        (>1 active subscription on the same plan for one customer)
  3. Customer impact in $           (current usage: what the duplicates add on top)
  4. Invoices already affected      (draft -> fix + refresh; finalized -> credit note)
  5. Duplicate events               (same payload, different transaction_id -> doubled quantities, a different bug)
  6. Audit trail                    (activity logs, if the plan tier allows it)

Exit code: 0 = clean, 1 = findings (so it can run as a scheduled guardrail).

--fix is DESTRUCTIVE with --apply. Several charges on one metric can be intentional
(filters, per-model prices, overrides). Review filters, plan overrides, the subscriptions
on the plan and the invoice impact with the customer first; run --fix (dry-run) and get
sign-off before --apply. Charges with different filters are never grouped as duplicates.

Run:  uv run python -m lago_case.s2_diagnose --customer saasco_demo_customer [--fix [--apply]]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from . import lago_http as lago


def _filters_key(charge: dict) -> str:
    return json.dumps(sorted((f.get("key"), sorted(f.get("values") or [])) for f in (charge.get("filters") or [])))


def _money(cents: float) -> str:
    return f"${cents / 100:,.2f}"


def duplicate_charges(plan: dict) -> dict[tuple, list[dict]]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for c in plan.get("charges") or []:
        groups[(c["billable_metric_code"], _filters_key(c))].append(c)
    return {k: sorted(v, key=lambda c: c["created_at"]) for k, v in groups.items() if len(v) > 1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", required=True, help="Lago external_customer_id")
    ap.add_argument("--fix", action="store_true", help="propose a fix for duplicate charges (dry-run)")
    ap.add_argument("--apply", action="store_true", help="with --fix: actually PUT the deduplicated plan")
    args = ap.parse_args()

    findings: list[str] = []
    subs = [s for s in lago.paginate("/subscriptions", "subscriptions", external_customer_id=args.customer)
            if s["status"] == "active"]
    print(f"Customer {args.customer}: {len(subs)} active subscription(s)\n")

    # 1. Duplicate charges per plan
    plans = {s["plan_code"] for s in subs}
    dup_by_plan: dict[str, dict] = {}
    for code in sorted(plans):
        plan = lago.get(f"/plans/{code}")["plan"]
        dups = duplicate_charges(plan)
        print(f"[1] Plan '{code}': {len(plan['charges'])} charges")
        if not dups:
            print("    OK: one charge per metric/filter")
            continue
        dup_by_plan[code] = {"plan": plan, "dups": dups}
        findings.append(f"plan '{code}' has duplicate charges for {sorted(k[0] for k in dups)}")
        for (metric, _), charges in sorted(dups.items()):
            original, *extra = charges
            print(f"    DUPLICATE {metric}: {len(charges)} charges")
            print(f"       original  {original['lago_id'][:8]}  created {original['created_at']}")
            for c in extra:
                print(f"       duplicate {c['lago_id'][:8]}  created {c['created_at']}   <-- when it broke")

    # 2. Duplicate subscriptions on the same plan
    by_plan: dict[str, list[dict]] = defaultdict(list)
    for s in subs:
        by_plan[s["plan_code"]].append(s)
    print("\n[2] Subscriptions per plan")
    for code, ss in by_plan.items():
        if len(ss) > 1:
            findings.append(f"{len(ss)} active subscriptions on plan '{code}'")
            print(f"    DUPLICATE: {len(ss)} active subscriptions on '{code}':")
            for s in sorted(ss, key=lambda s: s["created_at"]):
                print(f"       {s['external_id']}  created {s['created_at']}")
        else:
            print(f"    OK: 1 active subscription on '{code}'")

    # 3. Dollar impact from current usage
    print("\n[3] Current-period impact")
    for s in subs:
        u = lago.get(f"/customers/{args.customer}/current_usage", external_subscription_id=s["external_id"])["customer_usage"]
        per_metric: dict[str, list[int]] = defaultdict(list)
        for c in u["charges_usage"]:
            per_metric[c["billable_metric"]["code"]].append(int(c["amount_cents"]))
        total = sum(sum(v) for v in per_metric.values())
        expected = sum(v[0] for v in per_metric.values() if v)
        over = total - expected
        flag = "  <-- over-billing" if over else ""
        print(f"    {s['external_id']}: billed so far {_money(total)}, expected {_money(expected)}, "
              f"excess {_money(over)}{flag}")
        if over:
            findings.append(f"{s['external_id']} over-billed by {_money(over)} in the current period")

    # 4. Invoices already issued
    print("\n[4] Invoices")
    invoices = list(lago.paginate("/invoices", "invoices", external_customer_id=args.customer))
    if not invoices:
        print("    none yet (caught before the billing run)")
    for inv in invoices:
        detail = lago.get(f"/invoices/{inv['lago_id']}")["invoice"]
        counts: dict[str, int] = defaultdict(int)
        for f in detail.get("fees") or []:
            if f.get("item", {}).get("type") == "charge":
                counts[f["item"]["code"]] += 1
        dupe_lines = {k: v for k, v in counts.items() if v > 1}
        action = "fix plan, then refresh the draft" if inv["status"] == "draft" else "credit note for the duplicate lines"
        status = f"DUPLICATE LINES {dupe_lines} -> {action}" if dupe_lines else "OK"
        print(f"    {inv['number']} {inv['status']:<9} {_money(int(inv['total_amount_cents']))}  {status}")
        if dupe_lines:
            findings.append(f"invoice {inv['number']} ({inv['status']}) has duplicate lines")

    # 5. Duplicate events (same payload, different transaction_id)
    print("\n[5] Events")
    for s in subs:
        seen: dict[tuple, list[str]] = defaultdict(list)
        for e in lago.paginate("/events", "events", external_subscription_id=s["external_id"]):
            seen[(e["code"], e["timestamp"], json.dumps(e.get("properties"), sort_keys=True))].append(e["transaction_id"])
        dup_events = {k: v for k, v in seen.items() if len(v) > 1}
        n = sum(len(v) for v in seen.values())
        if dup_events:
            findings.append(f"{len(dup_events)} duplicated event payloads on {s['external_id']}")
            print(f"    {s['external_id']}: {n} events, {len(dup_events)} payloads sent more than once")
        else:
            print(f"    {s['external_id']}: {n} events, no duplicated payloads")

    # 6. Audit trail
    print("\n[6] Audit trail")
    try:
        lago.get("/activity_logs", per_page=5)
        print("    activity logs available: check who/what updated the plan at the timestamps above")
    except lago.LagoError as e:
        print(f"    activity logs not available on this tier ({e.status}); use charge created_at + the customer's job logs")

    # Optional fix: keep the oldest charge per (metric, filters)
    if args.fix:
        print("\n[fix] Deduplicate plan charges (keep the original = oldest charge per metric/filters)")
        for code, info in dup_by_plan.items():
            drop = {c["lago_id"] for charges in info["dups"].values() for c in charges[1:]}
            keep = [c for c in info["plan"]["charges"] if c["lago_id"] not in drop]
            payload = {"plan": {"charges": [
                {"id": c["lago_id"], "billable_metric_id": c["lago_billable_metric_id"],
                 "charge_model": c["charge_model"], "properties": c["properties"], "filters": c.get("filters") or []}
                for c in keep]}}
            print(f"    {code}: keep {len(keep)}, remove {len(drop)} -> PUT /plans/{code}")
            if args.apply:
                lago.put(f"/plans/{code}", payload)
                print("    applied. Re-run without --fix to confirm a clean report.")
            else:
                print("    dry-run (add --apply to execute)")

    print("\n" + ("FINDINGS:\n  - " + "\n  - ".join(findings) if findings else "CLEAN: no duplication found"))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
