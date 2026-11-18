# Section 1B: Follow-up email (sent within 24 hours)

**To:** VP of Engineering · **Cc:** Head of Finance, Staff Engineer, [AE]
**Subject:** Acme AI × Lago: your two open questions + next step
**Attachments:** Appendix A (committed spend + overage), Appendix B (Kafka integration note)

---

Hi [First name],

Thanks for yesterday, and for the sharp questions from the whole team. I owed you answers on two points, so here they are.

**For [Head of Finance]: committed spend + overage.** Lago produces the billing numbers; your ERP stays the ledger. Prepaid commitment is invoiced upfront, deferred, and recognized as usage consumes it. Overage is billed and recognized as it's used. Unused commitment or a true-up is its own invoice line, so your policy applies cleanly. Appendix A walks through a 3-month example and the implementation timeline.

**For [Staff Engineer]: Kafka.** Yes, no custom connector. Lago can read from your existing topic, or you publish to one we host. The main change on your side is mapping each message to the fields Lago bills on (Appendix B), and together we'll validate network access, credentials and throughput. If you send me one sample message **by Monday**, I'll bring it already mapped.

**Next step: two short sessions next week**

| Session | Who | What we'd cover |
|---|---|---|
| **45 min, technical** | Staff Engineer + data/infra; one of our engineers | Kafka pattern, your sample mapped, effort estimate |
| **30 min, finance** | Head of Finance; our finance specialist | The worked example against your contract shape |

Could you reply **by Friday** with one slot for each? Technical: **Tue 24 or Wed 25 Nov**. Finance: **Wed 25 or Thu 26 Nov** ([Head of Finance], feel free to answer directly). I'll send invites and a one-line agenda the same day.

Best,
Daniel
Solutions Engineer, Lago
