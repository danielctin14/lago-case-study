"""Section 3.3: store invoices from BOTH Stripe and Lago in one database (SQLite).

* Stripe invoices: Invoice.list (auto-paging), with their line items.
* Lago invoices: Lago SDK invoices.find_all (paged), then invoices.find for the fees
  (each fee carries its SKU, units, amount and service period).
* Upserts on (source, source_invoice_id): re-running refreshes and never duplicates.
* The customer key is shared (Stripe customer id = Lago external_customer_id), so
  the v_customer_billing view reconciles both systems with a plain GROUP BY.

Demo only: `--close-sample N` terminates N migrated Lago subscriptions so Lago issues
their final invoices now, instead of at the end of the billing period.

Run:  uv run python -m lago_case.s3_invoice_sync [--close-sample 3]
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import stripe
from lago_python_client.client import Client

from . import db
from .config import LAGO_API_KEY, LAGO_API_URL, require
from .s3_seed_stripe import init as stripe_init

lago = Client(api_key=require(LAGO_API_KEY, "LAGO_API_KEY"), api_url=LAGO_API_URL)


def _ts(epoch: int | None) -> str | None:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None


def sync_stripe(conn) -> int:
    n = 0
    for inv in stripe.Invoice.list(limit=100).auto_paging_iter():
        inv = inv.to_dict()
        sub_id = (inv.get("parent") or {}).get("subscription_details", {}).get("subscription") or inv.get("subscription")
        lines = [
            {"source": "stripe", "source_invoice_id": inv["id"], "line_id": ln["id"],
             "sku": ((ln.get("pricing") or {}).get("price_details") or {}).get("price") or (ln.get("price") or {}).get("lookup_key"),
             "description": ln.get("description"), "quantity": ln.get("quantity"), "amount_cents": ln.get("amount"),
             "period_start": _ts(ln["period"]["start"]), "period_end": _ts(ln["period"]["end"])}
            for ln in inv["lines"]["data"]
        ]
        db.upsert_invoice(conn, {
            "source": "stripe", "source_invoice_id": inv["id"], "number": inv.get("number"),
            "customer_external_id": inv["customer"], "subscription_external_id": sub_id,
            "status": inv["status"], "currency": inv["currency"].upper(),
            "subtotal_cents": inv.get("subtotal"), "tax_cents": sum(t.get("amount", 0) for t in inv.get("total_taxes") or []),
            "total_cents": inv.get("total"), "issued_at": _ts(inv.get("created")),
            "period_start": _ts(inv.get("period_start")), "period_end": _ts(inv.get("period_end")), "raw_json": inv,
        }, lines)
        n += 1
    return n


def sync_lago(conn) -> int:
    n, page = 0, 1
    while page:
        res = lago.invoices.find_all(options={"per_page": 100, "page": page})
        for summary in res["invoices"]:
            inv = lago.invoices.find(summary.lago_id).dict()  # detail includes fees
            fees = inv.get("fees") or []
            subs = inv.get("subscriptions") or []
            lines = [
                {"source": "lago", "source_invoice_id": inv["lago_id"], "line_id": f["lago_id"],
                 "sku": (f.get("item") or {}).get("code"), "description": (f.get("item") or {}).get("name"),
                 "quantity": float(f.get("units") or 0), "amount_cents": f.get("amount_cents"),
                 "period_start": f.get("from_date"), "period_end": f.get("to_date")}
                for f in fees
            ]
            db.upsert_invoice(conn, {
                "source": "lago", "source_invoice_id": inv["lago_id"], "number": inv["number"],
                "customer_external_id": (inv.get("customer") or {}).get("external_id"),
                "subscription_external_id": subs[0]["external_id"] if subs else None,
                "status": inv["status"], "currency": inv.get("currency"),
                "subtotal_cents": inv.get("sub_total_excluding_taxes_amount_cents"),
                "tax_cents": inv.get("taxes_amount_cents"), "total_cents": inv.get("total_amount_cents"),
                "issued_at": inv.get("issuing_date"),
                "period_start": min((ln["period_start"] for ln in lines if ln["period_start"]), default=None),
                "period_end": max((ln["period_end"] for ln in lines if ln["period_end"]), default=None),
                "raw_json": inv,
            }, lines)
            n += 1
        page = (res.get("meta") or {}).get("next_page")
    return n


def close_sample(n: int) -> None:
    """DEMO ONLY: terminate N migrated subscriptions -> Lago bills their usage to date now."""
    with db.connect() as conn:
        rows = conn.execute("SELECT stripe_subscription_id FROM migration_state WHERE status='done' "
                            "ORDER BY stripe_subscription_id LIMIT ?", (n,)).fetchall()
    for (sub_id,) in rows:
        try:
            lago.subscriptions.destroy(sub_id)
            print(f"  terminated {sub_id} (demo) -> final invoice")
        except Exception as e:
            print(f"  {sub_id}: {e}")
    time.sleep(8)  # invoices are generated asynchronously by Lago's workers


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--close-sample", type=int, default=0, help="DEMO: terminate N Lago subscriptions first")
    args = ap.parse_args()
    stripe_init()
    if args.close_sample:
        close_sample(args.close_sample)
    with db.connect() as conn:
        s, lg = sync_stripe(conn), sync_lago(conn)
        print(f"Synced {s} Stripe invoices and {lg} Lago invoices into {db.DB_PATH.name}")
        print("\nInvoices by source/status:")
        for r in conn.execute("SELECT source, status, COUNT(*) n, SUM(total_cents)/100.0 total "
                              "FROM invoices GROUP BY source, status ORDER BY source, status"):
            print(f"  {r['source']:<7} {r['status']:<10} {r['n']:>4}  ${r['total'] or 0:,.2f}")
        print("\nCustomers billed by both systems (v_customer_billing):")
        for r in conn.execute("SELECT * FROM v_customer_billing WHERE lago_invoices > 0 AND stripe_invoices > 0 LIMIT 5"):
            print(f"  {r['customer_external_id']}: Stripe {r['stripe_invoices']} inv ${r['stripe_total']:,.2f} | "
                  f"Lago {r['lago_invoices']} inv ${r['lago_total']:,.2f}")


if __name__ == "__main__":
    main()
