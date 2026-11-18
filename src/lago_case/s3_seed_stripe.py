"""Section 3 (setup): seed Stripe TEST mode with SaaSCo's legacy billing.

One product, four prices (mirrors the Lago catalog):
    Tokens, Storage, GB-S  -> metered prices backed by Stripe Billing Meters
    Seats                  -> licensed per-unit price (quantity = seats)
N customers, one active subscription each (default 100; the real company has 10,000).
Idempotent: looks up meters/prices by key and customers by seed index before creating.

Run:  uv run python -m lago_case.s3_seed_stripe [--count 100]
"""

from __future__ import annotations

import argparse
import random
from concurrent.futures import ThreadPoolExecutor

import stripe

from .config import STRIPE_API_KEY, require

SEED_TAG = "saasco_seed"
METERS = {  # lookup_key -> (meter event_name, display, unit price in cents as decimal string, aggregation)
    "saasco_tokens": ("saasco_tokens", "Tokens", "0.0002", "sum"),
    "saasco_storage": ("saasco_storage_gb", "Storage (GB)", "10", "last"),
    "saasco_gbs": ("saasco_gb_seconds", "GB-S", "0.00166667", "sum"),
}
SEATS_KEY, SEAT_CENTS = "saasco_seats", 2000


def init() -> None:
    key = require(STRIPE_API_KEY, "STRIPE_API_KEY")
    if not key.startswith("sk_test_"):
        raise SystemExit("Refusing to run: STRIPE_API_KEY is not a TEST key (sk_test_...)")
    stripe.api_key = key
    stripe.max_network_retries = 3  # Stripe SDK retries 429/5xx with backoff


def ensure_product() -> str:
    for p in stripe.Product.search(query=f"metadata['{SEED_TAG}']:'product'").auto_paging_iter():
        return p.id
    return stripe.Product.create(name="SaaSCo Platform", metadata={SEED_TAG: "product"}).id


def ensure_meter(event_name: str, display: str, aggregation: str) -> str:
    for m in stripe.billing.Meter.list(limit=100).auto_paging_iter():
        if m.event_name == event_name and m.status == "active":
            return m.id
    try:
        return stripe.billing.Meter.create(display_name=display, event_name=event_name,
                                           default_aggregation={"formula": aggregation}).id
    except stripe.InvalidRequestError:  # older API versions don't support 'last'
        return stripe.billing.Meter.create(display_name=display, event_name=event_name,
                                           default_aggregation={"formula": "sum"}).id


def ensure_prices(product_id: str) -> dict[str, str]:
    existing = {p.lookup_key: p.id for p in stripe.Price.list(
        lookup_keys=[*METERS, SEATS_KEY], limit=10, active=True).auto_paging_iter()}
    for key, (event_name, display, cents, agg) in METERS.items():
        if key not in existing:
            meter_id = ensure_meter(event_name, display, agg)
            existing[key] = stripe.Price.create(
                product=product_id, currency="usd", lookup_key=key, nickname=display,
                unit_amount_decimal=cents,
                recurring={"interval": "month", "usage_type": "metered", "meter": meter_id},
            ).id
    if SEATS_KEY not in existing:
        existing[SEATS_KEY] = stripe.Price.create(
            product=product_id, currency="usd", lookup_key=SEATS_KEY, nickname="Seats",
            unit_amount=SEAT_CENTS, recurring={"interval": "month", "usage_type": "licensed"},
        ).id
    return existing


def existing_seed_customers() -> set[int]:
    seen = set()
    for c in stripe.Customer.list(limit=100).auto_paging_iter():
        if (c.metadata or {}).get(SEED_TAG):
            seen.add(int(c.metadata[SEED_TAG]))
    return seen


def create_customer_with_subscription(i: int, prices: dict[str, str]) -> str:
    rnd = random.Random(i)  # deterministic per customer
    cus = stripe.Customer.create(
        name=f"SaaSCo Customer {i:05d}",
        email=f"billing+{i:05d}@saasco-demo.test",
        metadata={SEED_TAG: str(i)},
        idempotency_key=f"saasco-seed-customer-{i}",
    )
    stripe.Subscription.create(
        customer=cus.id,
        collection_method="send_invoice",  # no payment method needed in test mode
        days_until_due=30,
        items=[{"price": prices[k]} for k in METERS] + [{"price": prices[SEATS_KEY], "quantity": rnd.randint(1, 25)}],
        metadata={SEED_TAG: str(i)},
        idempotency_key=f"saasco-seed-subscription-{i}",
    )
    return cus.id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100)
    args = ap.parse_args()
    init()
    prices = ensure_prices(ensure_product())
    print("Stripe prices:", {k: v for k, v in prices.items()})
    todo = sorted(set(range(1, args.count + 1)) - existing_seed_customers())
    print(f"Creating {len(todo)} customers + subscriptions (already seeded: {args.count - len(todo)})")
    with ThreadPoolExecutor(max_workers=5) as pool:  # stays well under test-mode rate limits
        for n, _ in enumerate(pool.map(lambda i: create_customer_with_subscription(i, prices), todo), 1):
            if n % 25 == 0:
                print(f"  {n}/{len(todo)}")
    print("Done.")


if __name__ == "__main__":
    main()
