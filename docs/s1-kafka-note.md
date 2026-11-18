# Appendix B: Kafka ingestion, integration note

*For Acme AI's Staff Engineer.*

**No custom connector.** Lago consumes Kafka directly, in one of two ways: **(A)** Lago reads your existing topic (you grant broker/topic access), or **(B)** you produce to a topic Lago hosts for you (VPC peering or PrivateLink). Both run on Lago's ClickHouse event store, which Lago Cloud manages.

**The message shape Lago bills on:** `transaction_id` (unique; used for deduplication, so retries never double-bill), `external_subscription_id`, `code` (the metric, e.g. `llm_tokens`), `timestamp`, and `properties` (e.g. `{"tokens": 1250, "model": "large", "direction": "output"}`). If your messages carry these, there's nothing to build. If not, it's a small mapping step, not a connector. Together we'll also validate network access, credentials and throughput. The REST batch API takes the same schema, so you can pilot over REST and move to Kafka later.

**By Monday, to prepare the session:** one sample message (anonymized), your preference between A and B with any network constraints, and a rough volume (peak events/second, monthly total).
