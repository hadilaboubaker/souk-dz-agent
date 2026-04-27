"""Top-level pipeline: scrape -> normalize -> store -> detect opportunities -> report."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from pathlib import Path

from souk_dz.ai.normalizer import normalize
from souk_dz.analysis.database import ListingsDB
from souk_dz.analysis.opportunity import find_opportunities
from souk_dz.config import DATA_DIR, get_settings
from souk_dz.models import Listing
from souk_dz.reporting.email_sender import send_report
from souk_dz.reporting.excel import write_excel
from souk_dz.scrapers import all_scrapers

log = logging.getLogger(__name__)


async def run_pipeline() -> dict:
    settings = get_settings()
    log.info("Starting Souk-DZ pipeline (dry_run=%s)", settings.dry_run)

    # ---- 1. Scrape all sources concurrently ----
    scrapers = all_scrapers()
    raw_results = await asyncio.gather(*(scraper.safe_fetch() for scraper in scrapers))
    listings: list[Listing] = [item for sublist in raw_results for item in sublist]
    log.info("Collected %d raw listings from %d sources", len(listings), len(scrapers))

    if not listings:
        log.warning("No listings collected — aborting pipeline")
        return {"status": "no_listings", "total": 0}

    # ---- 2. Normalize via Gemini (batched) ----
    normalized = await normalize(listings)
    log.info("Normalized %d listings", len(normalized))

    # ---- 3. Persist + load history ----
    db = ListingsDB(settings.db_path)
    inserted = db.upsert(normalized)
    pruned = db.prune_older_than(int(settings.opportunity_config.get("history_days", 30)) * 2)
    log.info("DB upsert=%d, pruned=%d, total_rows=%d", inserted, pruned, db.count())

    # ---- 4. Detect opportunities ----
    opportunities = find_opportunities(normalized, db)
    log.info("Detected %d opportunities", len(opportunities))

    # ---- 5. Build Excel + send email ----
    today = date.today().isoformat()
    out_dir: Path = DATA_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    excel_path = out_dir / f"souk-dz-{today}.xlsx"
    write_excel(excel_path, normalized, opportunities)
    log.info("Excel written to %s", excel_path)

    sent = False
    if not settings.dry_run:
        sent = send_report(
            today=today,
            all_items=normalized,
            opportunities=opportunities,
            excel_path=excel_path,
        )

    return {
        "status": "ok",
        "total": len(normalized),
        "opportunities": len(opportunities),
        "email_sent": sent,
        "excel_path": str(excel_path),
    }
