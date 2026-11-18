#!/usr/bin/env bash
# Section 2: duplicated charges, curl-only diagnosis (read-only).
# Hand this to the customer: needs only curl + jq.
#
#   export LAGO_API_URL=https://api.getlago.com    # or http://localhost:3000 for self-hosted
#   export LAGO_API_KEY=...                         # Developers > API keys
#   ./scripts/s2_diagnose_curl.sh <external_customer_id>
set -euo pipefail

CUSTOMER="${1:?usage: $0 <external_customer_id>}"
API="${LAGO_API_URL:-http://localhost:3000}/api/v1"
AUTH="Authorization: Bearer ${LAGO_API_KEY:?set LAGO_API_KEY}"
lago() { curl -sS -f -H "$AUTH" "$API$1"; }

echo "== 1. Active subscriptions for $CUSTOMER (more than one per plan = duplicate subscriptions)"
SUBS=$(lago "/subscriptions?external_customer_id=$CUSTOMER&per_page=100")
echo "$SUBS" | jq -r '.subscriptions[] | select(.status=="active") | "  \(.external_id)  plan=\(.plan_code)  created=\(.created_at)"'
echo "$SUBS" | jq -r '[.subscriptions[] | select(.status=="active")] | group_by(.plan_code)[] | select(length>1)
  | "  !! \(length) active subscriptions on plan \(.[0].plan_code)"'

for PLAN in $(echo "$SUBS" | jq -r '[.subscriptions[] | select(.status=="active") | .plan_code] | unique[]'); do
  echo
  echo "== 2. Charges on plan $PLAN grouped by metric (count > 1 = duplicate charges; created_at = when it broke)"
  lago "/plans/$PLAN" | jq -r '.plan.charges | group_by(.billable_metric_code)[]
    | "  \(.[0].billable_metric_code): \(length) charge(s)" + (if length>1 then "  !! DUPLICATE" else "" end),
      (if length>1 then (.[] | "      \(.lago_id)  created \(.created_at)") else empty end)'
done

for SUB in $(echo "$SUBS" | jq -r '.subscriptions[] | select(.status=="active") | .external_id'); do
  echo
  echo "== 3. Current usage for $SUB (same metric listed twice = billed twice)"
  lago "/customers/$CUSTOMER/current_usage?external_subscription_id=$SUB" | jq -r '.customer_usage
    | "  total: \(.total_amount_cents|tonumber/100) \(.currency)",
      (.charges_usage | group_by(.billable_metric.code)[]
        | "  \(.[0].billable_metric.code): \(length) line(s), \(map(.amount_cents|tonumber)|add/100)")'
done

echo
echo "== 4. Invoices (draft = fix + refresh; finalized = credit note)"
lago "/invoices?external_customer_id=$CUSTOMER&per_page=100" | jq -r '.invoices[]
  | "  \(.number)  \(.status)  \(.total_amount_cents|tonumber/100) \(.currency)  issued \(.issuing_date)"'
