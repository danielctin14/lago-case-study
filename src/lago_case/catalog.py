"""SaaSCo catalog: one plan, four SKUs. Idempotent; safe to re-run.

    Tokens   -> usage charge, sum of `tokens`
    Storage  -> usage charge, max of `gb` over the period
    GB-S     -> usage charge, sum of `gb_seconds` (compute)
    Seats    -> usage charge on a RECURRING metric: unique count of `seat_id`
                (seat events with operation_type add/remove; the count carries over
                between periods). On self-hosted OSS Lago this is the way to bill
                per-customer seat counts: fixed charges exist, but changing their
                units per subscription returns 403 feature_unavailable (Premium).

Run:  uv run python -m lago_case.catalog
"""

from __future__ import annotations

from . import lago_http as lago
from .config import PLAN_CODE

METRICS = [
    {"code": "tokens", "name": "Tokens", "aggregation_type": "sum_agg", "field_name": "tokens"},
    {"code": "storage_gb", "name": "Storage (GB)", "aggregation_type": "max_agg", "field_name": "gb"},
    {"code": "gb_seconds", "name": "GB-S (compute)", "aggregation_type": "sum_agg", "field_name": "gb_seconds"},
    {"code": "seats", "name": "Seats", "aggregation_type": "unique_count_agg", "field_name": "seat_id", "recurring": True},
]
SKUS = (("tokens", "Tokens"), ("storage_gb", "Storage"), ("gb_seconds", "GB-S"), ("seats", "Seats"))

# Illustrative list prices (USD).
PRICES = {"tokens": "0.000002", "storage_gb": "0.10", "gb_seconds": "0.0000166667", "seats": "20"}


def ensure_metrics() -> dict[str, str]:
    """Create the billable metrics if missing; return {code: lago_id}."""
    ids = {}
    for m in METRICS:
        existing = lago.get_or_none(f"/billable_metrics/{m['code']}")
        if existing is None:
            existing = lago.post("/billable_metrics", {"billable_metric": {"recurring": False, **m}})
        ids[m["code"]] = existing["billable_metric"]["lago_id"]
    return ids


def usage_charges(metric_ids: dict[str, str]) -> list[dict]:
    return [
        {
            "billable_metric_id": metric_ids[code],
            "charge_model": "standard",
            "invoice_display_name": name,
            "properties": {"amount": PRICES[code]},
        }
        for code, name in SKUS
    ]


def plan_payload(code: str, metric_ids: dict[str, str], name: str = "SaaSCo Standard") -> dict:
    return {
        "plan": {
            "name": name,
            "code": code,
            "interval": "monthly",
            "amount_cents": 0,
            "amount_currency": "USD",
            "pay_in_advance": False,
            "charges": usage_charges(metric_ids),
        }
    }


def ensure_plan(code: str = PLAN_CODE) -> dict:
    metric_ids = ensure_metrics()
    existing = lago.get_or_none(f"/plans/{code}")
    if existing is None:
        existing = lago.post("/plans", plan_payload(code, metric_ids))
    return existing["plan"]


def main() -> None:
    plan = ensure_plan()
    print(f"Plan {plan['code']}: {len(plan.get('charges') or [])} charges")
    for c in plan.get("charges") or []:
        print(f"  charge  {c['billable_metric_code']:<11} {c['charge_model']}  {c['properties']}")


if __name__ == "__main__":
    main()
