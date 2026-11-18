"""Section 3.2: reconnect the usage event flow to Lago (Lago Python SDK).

Before:  product usage -> stripe.billing.MeterEvent.create(event_name="saasco_tokens", payload={...})
After:   product usage -> this forwarder -> lago.events.batch_create(...)

The usage source is simulated as a JSONL log (data/usage_stream.jsonl), the way a
product's usage outbox or a Kafka topic dump would look. The forwarder:
  * maps product usage types to Lago metric codes and property names
  * uses the product's own record id as transaction_id -> replays never double-bill
  * sends batches of up to 100 (Lago's batch limit); a batch is atomic, so if one
    is rejected it falls back to one-by-one to isolate the bad record
  * writes records it can't map or Lago rejects to data/dead_letter.jsonl

Run:  uv run python -m lago_case.s3_usage_forwarder --generate   # create a usage stream for migrated subs
      uv run python -m lago_case.s3_usage_forwarder              # forward it to Lago (safe to re-run)
"""

from __future__ import annotations

import argparse
import json
import random
import time
import uuid

from lago_python_client.client import Client
from lago_python_client.exceptions import LagoApiError
from lago_python_client.models import BatchEvent, Event

from . import db
from .config import LAGO_API_KEY, LAGO_API_URL, ROOT, require

STREAM = ROOT / "data" / "usage_stream.jsonl"
DEAD_LETTER = ROOT / "data" / "dead_letter.jsonl"
BATCH = 100

# product usage type -> (Lago billable metric code, property name)
MAPPING = {
    "llm_tokens": ("tokens", "tokens"),
    "storage_snapshot": ("storage_gb", "gb"),
    "compute": ("gb_seconds", "gb_seconds"),
}

lago = Client(api_key=require(LAGO_API_KEY, "LAGO_API_KEY"), api_url=LAGO_API_URL)


def generate(per_sub: int = 4) -> None:
    """Simulate the product's usage log for every migrated subscription."""
    with db.connect() as conn:
        rows = conn.execute("SELECT stripe_subscription_id FROM migration_state WHERE status='done'").fetchall()
    now = int(time.time())
    records = []
    for (sub_id,) in rows:
        rnd = random.Random(sub_id)
        for _ in range(per_sub):
            records += [
                {"id": str(uuid.UUID(int=rnd.getrandbits(128))), "subscription": sub_id, "type": "llm_tokens",
                 "value": rnd.randint(50_000, 2_000_000), "ts": now},
                {"id": str(uuid.UUID(int=rnd.getrandbits(128))), "subscription": sub_id, "type": "compute",
                 "value": rnd.randint(10_000, 400_000), "ts": now},
            ]
        records.append({"id": str(uuid.UUID(int=rnd.getrandbits(128))), "subscription": sub_id,
                        "type": "storage_snapshot", "value": rnd.randint(5, 500), "ts": now})
    # one record the product emits that has no price in Lago yet -> must go to dead letter, not vanish
    records.append({"id": "rec-unmapped-0001", "subscription": rows[0][0], "type": "gpu_hours", "value": 3, "ts": now})
    STREAM.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} usage records for {len(rows)} subscriptions -> {STREAM.relative_to(ROOT)}")


def to_event(rec: dict) -> Event | None:
    if rec["type"] not in MAPPING:
        return None
    code, prop = MAPPING[rec["type"]]
    return Event(transaction_id=rec["id"], external_subscription_id=rec["subscription"],
                 code=code, timestamp=rec["ts"], properties={prop: rec["value"]})


def dead_letter(rec: dict, reason: str) -> None:
    with DEAD_LETTER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "reason": reason}) + "\n")


def _rejections(e: LagoApiError) -> dict[int, dict] | None:
    """Per-record errors from a 422 batch response: {"error_details": {"0": {...}}}."""
    details = e.response.get("error_details") if isinstance(e.response, dict) else None
    try:
        return {int(k): v for k, v in (details or {}).items()} or None
    except (TypeError, ValueError):
        return None


def _already_ingested(err: dict) -> bool:
    return set(err) == {"transaction_id"} and err["transaction_id"] == ["value_already_exist"]


def send(batch: list[tuple[dict, Event]]) -> tuple[int, int, int]:
    """Send one batch (atomic in Lago). Returns (sent, already_ingested, dead).

    On a 422, Lago says which records failed and why. Records whose only error is a
    duplicate transaction_id were ingested before (a replay): count them, drop them,
    and resend the rest. Anything else is dead-lettered with Lago's reason.
    """
    sent = dup = dead = 0
    while batch:
        for attempt in range(4):
            try:
                lago.events.batch_create(BatchEvent(events=[e for _, e in batch]))
                return sent + len(batch), dup, dead
            except LagoApiError as e:
                if e.status_code >= 500 and attempt < 3:
                    time.sleep(2**attempt)
                    continue
                rejected = _rejections(e) if e.status_code == 422 else None
                if rejected is None:  # unknown error shape: dead-letter the whole batch
                    for rec, _ in batch:
                        dead_letter(rec, f"lago {e.status_code}: {str(e)[:200]}")
                    return sent, dup, dead + len(batch)
                for i, err in rejected.items():
                    if _already_ingested(err):
                        dup += 1
                    else:
                        dead_letter(batch[i][0], f"lago 422: {json.dumps(err)}")
                        dead += 1
                batch = [b for i, b in enumerate(batch) if i not in rejected]
                break
    return sent, dup, dead


def forward() -> None:
    records = [json.loads(line) for line in STREAM.read_text(encoding="utf-8").splitlines() if line.strip()]
    mapped, dead = [], 0
    for rec in records:
        ev = to_event(rec)
        if ev is None:
            dead_letter(rec, f"no Lago metric mapped for usage type '{rec['type']}'")
            dead += 1
        else:
            mapped.append((rec, ev))
    sent = dup = 0
    t0 = time.time()
    for i in range(0, len(mapped), BATCH):
        s, u, d = send(mapped[i:i + BATCH])
        sent, dup, dead = sent + s, dup + u, dead + d
    print(f"Forwarded {sent} new events, skipped {dup} already ingested, in {time.time() - t0:.1f}s "
          f"({(len(mapped) + BATCH - 1) // BATCH} batches); dead-lettered {dead} -> {DEAD_LETTER.relative_to(ROOT)}")


def show_sample_usage(n: int = 3) -> None:
    time.sleep(3)
    with db.connect() as conn:
        rows = conn.execute("SELECT stripe_customer_id, stripe_subscription_id FROM migration_state "
                            "WHERE status='done' ORDER BY stripe_subscription_id LIMIT ?", (n,)).fetchall()
    for cus, sub in rows:
        u = lago.customers.current_usage(cus, sub)
        lines = ", ".join(f"{c.billable_metric.code}={float(c.units):g}" for c in u.charges_usage)
        print(f"  {sub}: ${int(u.total_amount_cents) / 100:,.2f}  ({lines})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true", help="(re)create the simulated usage stream")
    args = ap.parse_args()
    if args.generate:
        generate()
        return
    forward()
    print("Current usage in Lago (sample):")
    show_sample_usage()


if __name__ == "__main__":
    main()
