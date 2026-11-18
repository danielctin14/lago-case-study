"""Shared configuration, loaded from .env (see .env.example)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

LAGO_API_URL = os.getenv("LAGO_API_URL", "http://localhost:3000").rstrip("/")
LAGO_API_KEY = os.getenv("LAGO_API_KEY", "")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
DB_PATH = ROOT / os.getenv("DB_PATH", "data/billing.db")

# The SaaSCo catalog: one plan, four SKUs (shared by Section 2 and Section 3).
PLAN_CODE = "saasco_standard"


def require(value: str, name: str) -> str:
    if not value or "replace" in value:
        raise SystemExit(f"Missing {name}: set it in {ROOT / '.env'}")
    return value
