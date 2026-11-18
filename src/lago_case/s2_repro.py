"""Section 2: reproduce SaaSCo's duplicated charges (Tokens, Storage, GB-S, Seats).

Scenarios (all on an isolated plan/customer, never on the Section 3 catalog):

  sync-append  (default, the realistic one)
      Day 0  "automation v1" creates the plan + subscription: 4 SKUs, all good.
      Day N  a "price sync" job is added. It GETs the plan, appends the desired
             charges (built from config, so without Lago `id`s) and PUTs it back.
             Lago treats id-less charges as NEW charges -> every SKU is now on
             the plan twice, and every subscription on that plan is billed twice.
  direct
      POST /plans with each metric attached twice, then subscribe. Lago accepts it
      (several charges per metric is a legitimate feature, normally used with filters).
  duplicate-subscription
      A different root cause with the same customer-visible symptom: the
      automation creates a 2nd subscription with a fresh external_id on each run.

Run:  uv run python -m lago_case.s2_repro [--scenario sync-append|direct|duplicate-subscription]
"""

from __future__ import annotations

import argparse
import time
import uuid

from . import catalog
from . import lago_http as lago

PLAN = "saasco_standard_s2"
CUSTOMER = "saasco_demo_customer"
SUBSCRIPTION = "sub_saasco_demo_001"
SEATS = 5


def reset() -> None:
    """Start from a clean slate so the demo is repeatable."""
    if lago.get_or_none(f"/customers/{CUSTOMER}"):
        for sub in lago.paginate("/subscriptions", "subscriptions", external_customer_id=CUSTOMER):
            lago.delete(f"/subscriptions/{sub['external_id']}")
    if lago.get_or_none(f"/plans/{PLAN}"):
        lago.delete(f"/plans/{PLAN}")


def ensure_customer() -> None:
    lago.post("/customers", {"customer": {"external_id": CUSTOMER, "name": "SaaSCo demo customer", "currency": "USD"}})


def subscribe(external_id: str) -> dict:
    return lago.post(
        "/subscriptions",
        {"subscription": {"external_customer_id": CUSTOMER, "plan_code": PLAN,
                          "external_id": external_id, "billing_time": "calendar"}},
    )["subscription"]


def plan_shape() -> str:
    p = lago.get(f"/plans/{PLAN}")["plan"]
    codes = sorted(c["billable_metric_code"] for c in p["charges"])
    return f"{len(p['charges'])} charges {codes}"


def automation_v1_create_plan() -> None:
    lago.post("/plans", catalog.plan_payload(PLAN, catalog.ensure_metrics(), name="SaaSCo Standard (S2 demo)"))


def automation_v2_price_sync() -> None:
    """The buggy job: GET + append desired charges (no ids) + PUT."""
    current = lago.get(f"/plans/{PLAN}")["plan"]
    keep = [
        {"id": c["lago_id"], "billable_metric_id": c["lago_billable_metric_id"],
         "charge_model": c["charge_model"], "properties": c["properties"]}
        for c in current["charges"]
    ]
    desired = catalog.usage_charges(catalog.ensure_metrics())  # built from config -> no `id`
    lago.put(f"/plans/{PLAN}", {"plan": {"charges": keep + desired}})


def send_usage(external_subscription_id: str) -> None:
    now = int(time.time())
    usage = [("tokens", {"tokens": 1_500_000}), ("storage_gb", {"gb": 120}), ("gb_seconds", {"gb_seconds": 900_000})]
    usage += [("seats", {"seat_id": f"seat_{i}"}) for i in range(1, SEATS + 1)]
    lago.post("/events/batch", {"events": [
        {"transaction_id": f"s2-{external_subscription_id}-{code}-{i}-{now}",
         "external_subscription_id": external_subscription_id,
         "code": code, "timestamp": now, "properties": props}
        for i, (code, props) in enumerate(usage)
    ]})


def show_usage(external_subscription_id: str) -> None:
    time.sleep(3)  # usage is computed asynchronously from events
    u = lago.get(f"/customers/{CUSTOMER}/current_usage", external_subscription_id=external_subscription_id)["customer_usage"]
    print(f"  current usage for {external_subscription_id}: total ${int(u['total_amount_cents']) / 100:,.2f}")
    for c in sorted(u["charges_usage"], key=lambda c: c["billable_metric"]["code"]):
        print(f"    {c['billable_metric']['code']:<11} units={str(c['units']):<10} "
              f"${int(c['amount_cents']) / 100:>8,.2f}  (charge {c['charge']['lago_id'][:8]})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="sync-append", choices=["sync-append", "direct", "duplicate-subscription"])
    args = ap.parse_args()

    print(f"Resetting demo plan '{PLAN}' and customer '{CUSTOMER}'...")
    reset()
    ensure_customer()

    if args.scenario == "direct":
        body = catalog.plan_payload(PLAN, catalog.ensure_metrics(), name="SaaSCo Standard (S2 demo)")
        body["plan"]["charges"] += catalog.usage_charges(catalog.ensure_metrics())
        lago.post("/plans", body)
        print(f"POST /plans with every SKU twice -> accepted: {plan_shape()}")
        subscribe(SUBSCRIPTION)
        send_usage(SUBSCRIPTION)
        show_usage(SUBSCRIPTION)
    else:
        print("Day 0: automation v1 creates plan + subscription")
        automation_v1_create_plan()
        subscribe(SUBSCRIPTION)
        print(f"  plan: {plan_shape()}")
        if args.scenario == "sync-append":
            print("Day N: new 'price sync' job runs (GET plan -> append desired charges without ids -> PUT)")
            automation_v2_price_sync()
            print(f"  plan: {plan_shape()}   <-- every SKU twice")
            send_usage(SUBSCRIPTION)
            show_usage(SUBSCRIPTION)
        else:
            print("Day N: automation re-runs and creates a NEW subscription with a fresh external_id")
            dup = f"sub_saasco_demo_{uuid.uuid4().hex[:6]}"
            subscribe(dup)
            subs = list(lago.paginate("/subscriptions", "subscriptions", external_customer_id=CUSTOMER))
            print(f"  active subscriptions for {CUSTOMER}: {[s['external_id'] for s in subs]}")
            for s in (SUBSCRIPTION, dup):
                send_usage(s)
                show_usage(s)

    print(f"\nNow run:  uv run python -m lago_case.s2_diagnose --customer {CUSTOMER}")


if __name__ == "__main__":
    main()
