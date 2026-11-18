"""Concatenate docs/*.md into one Notion-importable page, rewriting relative links to GitHub.

Run:  uv run python scripts/build_notion.py https://github.com/<user>/<repo>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ORDER = [
    "s1-debrief.md", "s1-email.md", "s1-finance-onepager.md", "s1-kafka-note.md",
    "s2-duplicate-charges.md", "s3-stripe-migration.md", "s4-iot-gateways.md", "s5-vortex-bonus.md",
]
# Sections of this same page: referenced by name (Markdown anchors don't survive a Notion import).
SECTION_NAMES = {
    "s1-debrief.md": "Section 1A (debrief)", "s1-email.md": "Section 1B (email)",
    "s1-finance-onepager.md": "Appendix A (finance one-pager)", "s1-kafka-note.md": "Appendix B (Kafka note)",
    "s2-duplicate-charges.md": "Section 2", "s3-stripe-migration.md": "Section 3",
    "s4-iot-gateways.md": "Section 4", "s5-vortex-bonus.md": "Bonus",
}


def rewrite_links(text: str, repo: str) -> str:
    def fix(m: re.Match) -> str:
        label, target = m.group(1), m.group(2)
        if target.startswith(("http", "#", "mailto:")):
            return m.group(0)
        clean = target.removeprefix("../").removeprefix("./")
        if clean in SECTION_NAMES:  # another part of this same page -> plain reference
            return f"**{SECTION_NAMES[clean]}** (below)"
        path = clean if clean.startswith(("src/", "scripts/")) else f"docs/{clean}"
        return f"[{label}]({repo}/blob/main/{path})"
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", fix, text)


def main() -> None:
    repo = (sys.argv[1] if len(sys.argv) > 1 else "https://github.com/OWNER/REPO").rstrip("/")
    parts = [
        "# Lago: Solutions Engineer case study (Daniel)\n",
        f"> Code and reproducible setup: **{repo}**. Technical experiments were run against a self-hosted Lago v1.57.0 "
        "(PostgreSQL event store) and Stripe test mode; proposed production designs are marked as untested. "
        "Evidence tags: ✅ tested · 📘 documented · ⚠️ to confirm.\n",
        "## Results at a glance\n",
        "| Section | Outcome | Tested ✅ | Still unverified ⚠️ |",
        "|---|---|---|---|",
        "| **1. Acme AI follow-up** | Debrief (deal health, stakeholders, owners and deadlines) and a short email asking for two dated sessions; finance and Kafka appendices | Product claims checked against Lago docs | Which tier includes Kafka ingestion |",
        "| **2. SaaSCo duplicate charges** | Root cause: a merge-and-PUT plan sync duplicates every SKU. Diagnostic, reviewed fix, customer message | 3 scenarios reproduced; $260 billed instead of $130; diagnostic exit 1 → 0 after fix | curl/jq variant not executed |",
        "| **3. Stripe → Lago migration** | Stripe ids reused as Lago ids; idempotent migration (Lago SDK); replay-safe usage; both invoice sets in SQLite | 100/100 migrated, re-run creates 0; replay 0 new / 900 skipped; 108 invoices; reconciliation caught cutover double-billing | 10,000-scale run; period-end cutover; ClickHouse deduplication |",
        "| **4. Gateway pricing** | Base: config + custom. VPN allowance: custom. Trial: partly native. A Lago-managed job proposed, subject to approval | Prorated tiers; trial waives the base fee only; pooled vs per-gateway allowance ($10 vs $50); Premium 403s | Draft-hold of advance-billed charges; free-plan trial; pre-start events |",
        "| **Bonus: Vortex AI** | One-page 90-day plan, three phases with measurable exit criteria | n/a (strategy) | n/a |",
        "",
    ]
    for name in ORDER:
        parts.append("\n---\n")
        text = rewrite_links((DOCS / name).read_text(encoding="utf-8"), repo)
        parts.append(text)
    out = DOCS / "_notion-submission.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB) with links to {repo}")


if __name__ == "__main__":
    main()
