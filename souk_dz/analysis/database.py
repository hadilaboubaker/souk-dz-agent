"""SQLite-backed history of normalized listings used for price comparison."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from souk_dz.models import NormalizedListing

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,
    source_label    TEXT    NOT NULL,
    external_id     TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    canonical_name  TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    cluster_key     TEXT    NOT NULL,
    brand           TEXT,
    is_used         INTEGER,
    price_dzd       REAL,
    wilaya          TEXT,
    contact         TEXT,
    url             TEXT,
    posted_at       TEXT,
    scraped_at      TEXT    NOT NULL,
    payload_json    TEXT    NOT NULL,
    UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_listings_cluster_price ON listings (cluster_key, price_dzd);
CREATE INDEX IF NOT EXISTS idx_listings_scraped_at  ON listings (scraped_at);
"""


class ListingsDB:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ writes

    def upsert(self, items: list[NormalizedListing]) -> int:
        if not items:
            return 0
        rows = []
        for item in items:
            listing = item.listing
            rows.append(
                (
                    listing.source.value,
                    listing.source_label,
                    listing.external_id,
                    listing.title,
                    item.canonical_name,
                    item.category,
                    item.cluster_key,
                    item.brand,
                    int(item.is_used) if item.is_used is not None else None,
                    listing.price_dzd,
                    listing.wilaya,
                    listing.contact,
                    str(listing.url) if listing.url else None,
                    listing.posted_at.isoformat() if listing.posted_at else None,
                    listing.scraped_at.isoformat(),
                    item.model_dump_json(),
                )
            )
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO listings (
                    source, source_label, external_id, title, canonical_name,
                    category, cluster_key, brand, is_used, price_dzd,
                    wilaya, contact, url, posted_at, scraped_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, external_id) DO UPDATE SET
                    title = excluded.title,
                    canonical_name = excluded.canonical_name,
                    category = excluded.category,
                    cluster_key = excluded.cluster_key,
                    brand = excluded.brand,
                    is_used = excluded.is_used,
                    price_dzd = excluded.price_dzd,
                    wilaya = excluded.wilaya,
                    contact = excluded.contact,
                    url = excluded.url,
                    scraped_at = excluded.scraped_at,
                    payload_json = excluded.payload_json
                """,
                rows,
            )
        return len(rows)

    # ------------------------------------------------------------------ reads

    def cluster_prices(self, cluster_key: str, history_days: int) -> list[float]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=history_days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """
                SELECT price_dzd FROM listings
                WHERE cluster_key = ?
                  AND price_dzd IS NOT NULL
                  AND price_dzd > 0
                  AND scraped_at >= ?
                """,
                (cluster_key, cutoff),
            )
            return [row[0] for row in cur.fetchall()]

    def prune_older_than(self, days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM listings WHERE scraped_at < ?", (cutoff,))
            return cur.rowcount or 0

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
