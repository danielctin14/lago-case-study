"""Section 3.1: migrate Customers + Subscriptions from Stripe to Lago (Lago Python SDK).

Design choices (the ones that matter at 10,000 subscriptions):
  * IDs carry over: Lago customer.external_id = Stripe customer id,
    Lago subscription.external_id = Stripe subscription id. No mapping table is
    needed, and the usage stream can switch destination without a lookup.
  * Idempotent + resumable: a SQLite checkpoint per subscription, plus a Lago
    existence check. Re-running only processes what's missing or failed.
  * Seats (Stripe licensed quantity) become N `seats` add-events on Lago's recurring
    metric, with deterministic transaction_ids so a retry never adds a seat.
  * Cutover timing: --start now (demo) or --start period_end (production: Lago
    takes over exactly when the current Stripe period ends, so nothing is billed twice).
  * Bounded concurrency + retries: the SDK retries 429s; we retry 5xx and record failures.

Run:  uv run python -m lago_case.s3_migrate --dry-run
      uv run python -m lago_case.s3_migrate --start now
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import stripe
from lago_python_client.client import Client
from lago_python_client.exceptions import LagoApiError
from lago_python_client.models import BatchEvent, Customer, Event, Metadata, MetadataList, Subscription

from . import db
from .config import LAGO_API_KEY, LAGO_API_URL, PLAN_CODE, require
from .s3_seed_stripe import SEATS_KEY, init as stripe_init

lago = Client(api_key=require(LAGO_API_KEY, "LAGO_API_KEY"), api_url=LAGO_API_URL)


def stripe_subscriptions():
    """Every active Stripe subscription, with its customer expanded (100 per page)."""
    for s in stripe.Subscription.list(status="active", limit=100, expand=["data.customer"]).auto_paging_iter():
        yield s.to_dict()  # stripe-python v17 objects aren't dicts


def period_end(sub) -> int:
    # Newer Stripe API versions moved current_period_end onto subscription items.
    return sub.get("current_period_end") or sub["items"]["data"][0]["current_period_end"]


def seats_of(sub) -> int:
    for item in sub["items"]["data"]:
        if item["price"].get("lookup_key") == SEATS_KEY:
            return int(item.get("quantity") or 0)
    return 0


def to_lago(sub, start: str) -> tuple[Customer, Subscription, int, int]:
    cus = sub["customer"]
    customer = Customer(
        external_id=cus["id"],
        name=cus.get("name"),
        email=cus.get("email"),
        currency=sub["currency"].upper(),
        metadata=MetadataList(__root__=[Metadata(key="migrated_from", value="stripe", display_in_invoice=False)]),
    )
    starts_at = int(time.time()) if start == "now" else period_end(sub)
    subscription = Subscription(
        external_customer_id=cus["id"],
        external_id=sub["id"],
        plan_code=PLAN_CODE,
        billing_time="anniversary",  # keep each customer's billing date
        subscription_at=datetime.fromtimestamp(starts_at, timezone.utc).isoformat(),
    )
    return customer, subscription, seats_of(sub), starts_at


def lago_subscription_exists(external_id: str) -> bool:
    try:
        lago.subscriptions.find(external_id)
        return True
    except LagoApiError as e:
        if e.status_code == 404:
            return False
        raise


def migrate_one(sub, start: str) -> tuple[str, str, int]:
    customer, subscription, seats, starts_at = to_lago(sub, start)
    for attempt in range(4):
        try:
            lago.customers.create(customer)  # Lago upserts customers by external_id
            if not lago_subscription_exists(subscription.external_id):
                lago.subscriptions.create(subscription)
            if seats and start == "now":
                lago.events.batch_create(BatchEvent(events=[
                    Event(transaction_id=f"migration-{sub['id']}-seat-{n}",  # deterministic -> idempotent
                          external_subscription_id=sub["id"], code="seats",
                          timestamp=starts_at, properties={"seat_id": f"{sub['id']}-seat-{n}"})
                    for n in range(1, seats + 1)
                ]))
            return sub["id"], customer.external_id, seats
        except LagoApiError as e:
            if e.status_code < 500 or attempt == 3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", choices=["now", "period_end"], default="now")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    stripe_init()

    t0 = time.time()
    subs = list(stripe_subscriptions())
    read_s = time.time() - t0
    print(f"Stripe: {len(subs)} active subscriptions read in {read_s:.1f}s")

    if args.dry_run:
        for s in subs[:3]:
            c, sb, seats, _ = to_lago(s, args.start)
            print(f"  {c.external_id} '{c.name}' -> Lago customer; {sb.external_id} -> plan {sb.plan_code}, "
                  f"starts {sb.subscription_at}, seats={seats}")
        print(f"  ... {len(subs)} total. Dry run: nothing written.")
        return

    with db.connect() as conn:
        done = db.migrated_ids(conn)
    todo = [s for s in subs if s["id"] not in done]
    print(f"Already migrated (checkpoint): {len(done)}. To migrate now: {len(todo)}")

    ok = failed = 0
    t1 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool, db.connect() as conn:
        futures = {pool.submit(migrate_one, s, args.start): s for s in todo}
        for f in as_completed(futures):
            s = futures[f]
            try:
                sub_id, cus_id, seats = f.result()
                db.mark_migration(conn, sub_id, cus_id, "done", seats)
                ok += 1
            except Exception as e:  # recorded, retried on next run
                db.mark_migration(conn, s["id"], s["customer"]["id"], "failed", error=str(e)[:500])
                failed += 1
    elapsed = time.time() - t1
    rate = ok / elapsed if elapsed and ok else 0
    print(f"Migrated {ok}, failed {failed} in {elapsed:.1f}s ({rate:.1f} subscriptions/s)")
    if rate:
        print(f"Extrapolated for 10,000 subscriptions: ~{(10_000 / rate) / 60:.0f} min "
              f"(+ ~{read_s * 100 / 60:.1f} min to page through Stripe)")

    # Reconciliation: does Lago hold every Stripe subscription now?
    missing = [s["id"] for s in subs if not lago_subscription_exists(s["id"])]
    print(f"Reconciliation: Stripe {len(subs)} | Lago {len(subs) - len(missing)} | missing {len(missing)}")
    if missing:
        print("  missing:", missing[:10])


if __name__ == "__main__":
    main()
