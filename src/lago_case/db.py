"""SQLite storage: migration checkpoints + invoices from BOTH Stripe and Lago.

Why SQLite: zero setup, a single file reviewers can open, and enough SQL to show
the reconciliation view Finance would actually use during a migration.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS migration_state (
    stripe_subscription_id TEXT PRIMARY KEY,
    stripe_customer_id     TEXT NOT NULL,
    status                 TEXT NOT NULL,          -- done | failed
    seats                  INTEGER,
    error                  TEXT,
    updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    source                 TEXT NOT NULL,          -- 'stripe' | 'lago'
    source_invoice_id      TEXT NOT NULL,
    number                 TEXT,
    customer_external_id   TEXT,                   -- Stripe customer id (= Lago external_customer_id)
    subscription_external_id TEXT,                 -- Stripe subscription id (= Lago external_id)
    status                 TEXT,
    currency               TEXT,
    subtotal_cents         INTEGER,
    tax_cents              INTEGER,
    total_cents            INTEGER,
    issued_at              TEXT,
    period_start           TEXT,
    period_end             TEXT,
    raw_json               TEXT NOT NULL,
    synced_at              TEXT NOT NULL,
    PRIMARY KEY (source, source_invoice_id)
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    source                 TEXT NOT NULL,
    source_invoice_id      TEXT NOT NULL,
    line_id                TEXT NOT NULL,
    sku                    TEXT,
    description            TEXT,
    quantity               REAL,
    amount_cents           INTEGER,
    period_start           TEXT,
    period_end             TEXT,
    PRIMARY KEY (source, source_invoice_id, line_id)
);

-- One row per customer: what each system invoiced. This is the view Finance
-- watches during a parallel run / cutover.
CREATE VIEW IF NOT EXISTS v_customer_billing AS
SELECT customer_external_id,
       SUM(CASE WHEN source = 'stripe' THEN 1 ELSE 0 END)                  AS stripe_invoices,
       SUM(CASE WHEN source = 'stripe' THEN total_cents ELSE 0 END) / 100.0 AS stripe_total,
       SUM(CASE WHEN source = 'lago'   THEN 1 ELSE 0 END)                  AS lago_invoices,
       SUM(CASE WHEN source = 'lago'   THEN total_cents ELSE 0 END) / 100.0 AS lago_total
FROM invoices
GROUP BY customer_external_id;
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def mark_migration(conn, sub_id: str, cus_id: str, status: str, seats: int | None = None, error: str | None = None):
    conn.execute(
        """INSERT INTO migration_state VALUES (?,?,?,?,?,?)
           ON CONFLICT(stripe_subscription_id) DO UPDATE SET
             status=excluded.status, seats=excluded.seats, error=excluded.error, updated_at=excluded.updated_at""",
        (sub_id, cus_id, status, seats, error, now_iso()),
    )


def migrated_ids(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT stripe_subscription_id FROM migration_state WHERE status='done'")}


def upsert_invoice(conn, row: dict, lines: list[dict]) -> None:
    row = {**row, "raw_json": json.dumps(row["raw_json"], default=str), "synced_at": now_iso()}
    cols = list(row)
    conn.execute(
        f"INSERT INTO invoices ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
        f"ON CONFLICT(source, source_invoice_id) DO UPDATE SET "
        + ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("source", "source_invoice_id")),
        [row[c] for c in cols],
    )
    conn.execute("DELETE FROM invoice_lines WHERE source=? AND source_invoice_id=?", (row["source"], row["source_invoice_id"]))
    for ln in lines:
        lcols = list(ln)
        conn.execute(f"INSERT INTO invoice_lines ({','.join(lcols)}) VALUES ({','.join('?' * len(lcols))})",
                     [ln[c] for c in lcols])
