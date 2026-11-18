# Lago Solutions Engineer case study: Daniel

The written answers live in [`docs/`](docs/) (also published as one Notion page). The code for the two hands-on sections is in [`src/lago_case/`](src/lago_case/). Technical experiments were run against a **self-hosted Lago v1.57.0** and **Stripe test mode**; proposed production workflows are marked as untested. The migration was verified on 100 subscriptions; the 10,000-subscription rollout is a proposed plan pending load testing.

| Section | Write-up | Code |
|---|---|---|
| 1. Acme AI: demo debrief and follow-up | [debrief](docs/s1-debrief.md) · [email](docs/s1-email.md) · [finance one-pager](docs/s1-finance-onepager.md) · [Kafka note](docs/s1-kafka-note.md) | – |
| 2. SaaSCo: duplicated charges | [s2-duplicate-charges.md](docs/s2-duplicate-charges.md) | [s2_repro.py](src/lago_case/s2_repro.py) · [s2_diagnose.py](src/lago_case/s2_diagnose.py) · [curl version](scripts/s2_diagnose_curl.sh) |
| 3. Stripe → Lago migration | [s3-stripe-migration.md](docs/s3-stripe-migration.md) | [s3_migrate.py](src/lago_case/s3_migrate.py) · [s3_usage_forwarder.py](src/lago_case/s3_usage_forwarder.py) · [s3_invoice_sync.py](src/lago_case/s3_invoice_sync.py) |
| 4. Connected-gateway vendor | [s4-iot-gateways.md](docs/s4-iot-gateways.md) | (experiments run on the local instance) |
| Bonus: Vortex AI 90-day plan | [s5-vortex-bonus.md](docs/s5-vortex-bonus.md) | – |

## Findings worth knowing (all ✅ observed on Lago v1.57.0)
- `PUT /plans` with existing charges (with ids) **plus** new ones (without ids) **duplicates** them. That's the SaaSCo root cause. `charges: []` removes every charge.
- On self-hosted open source, changing **fixed-charge units per subscription** is Premium (`403 feature_unavailable`). That's why Seats is a recurring unique-count metric here.
- With the default PostgreSQL event store, a duplicate `transaction_id` gets a per-record `422 value_already_exist`, which makes replays safe to detect and skip (the ClickHouse store behaves differently; re-verify for Kafka).
- Events stamped **before** a subscription's start are stored but **not billed**.
- The trial waives the plan's base fee only; usage charges accrue during the trial.

## Run it

**Prerequisites:** Docker, [uv](https://docs.astral.sh/uv/), a Stripe **test-mode** secret key.

```bash
# 1) Lago, self-hosted (outside this repo)
git clone --depth 1 https://github.com/getlago/lago.git ../lago-oss && cd ../lago-oss
echo "LAGO_RSA_PRIVATE_KEY=\"$(openssl genrsa 2048 | openssl base64 -A)\"" > .env
cat >> .env <<'EOF'
LAGO_CREATE_ORG=true
LAGO_ORG_NAME=SaaSCo Sandbox
LAGO_ORG_USER_EMAIL=admin@saasco.local
LAGO_ORG_USER_PASSWORD=change-me
LAGO_ORG_API_KEY=<any-uuid-you-choose>
EOF
docker compose up -d && cd -          # API on http://localhost:3000, UI on http://localhost

# 2) This repo
cp .env.example .env                   # set LAGO_API_KEY (the uuid above) and STRIPE_API_KEY=sk_test_...
uv sync
uv run python -m lago_case.catalog     # SaaSCo plan: Tokens, Storage, GB-S, Seats

# Section 2
uv run python -m lago_case.s2_repro                                   # also: --scenario direct | duplicate-subscription
uv run python -m lago_case.s2_diagnose --customer saasco_demo_customer         # exit 1 = findings
uv run python -m lago_case.s2_diagnose --customer saasco_demo_customer --fix --apply

# Section 3
uv run python -m lago_case.s3_seed_stripe --count 100
uv run python -m lago_case.s3_migrate --dry-run
uv run python -m lago_case.s3_migrate --start now                    # production: --start period_end
uv run python -m lago_case.s3_usage_forwarder --generate
uv run python -m lago_case.s3_usage_forwarder                         # safe to re-run
uv run python -m lago_case.s3_invoice_sync --close-sample 3           # demo: bill 3 subs now
```

The invoices land in `data/billing.db` (SQLite). Try `SELECT * FROM v_customer_billing;`.
