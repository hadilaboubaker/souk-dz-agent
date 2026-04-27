"""Detect 'opportunity' listings — items priced significantly below the median.

Strategy:
  1. Group ``NormalizedListing`` by ``cluster_key``.
  2. Combine the current run with the historical prices in the SQLite store so
     small batches still get a meaningful baseline.
  3. Compute the median price for each cluster and flag listings priced at
     least ``min_discount_percent`` below that median.
  4. Rank opportunities by a composite score that rewards both the absolute
     savings and the size of the comparison sample.
"""
from __future__ import annotations

import logging
import statistics
from collections import defaultdict

from souk_dz.analysis.database import ListingsDB
from souk_dz.config import get_settings
from souk_dz.models import NormalizedListing, Opportunity

log = logging.getLogger(__name__)


def find_opportunities(
    items: list[NormalizedListing],
    db: ListingsDB,
) -> list[Opportunity]:
    if not items:
        return []
    cfg = get_settings().opportunity_config
    min_discount = float(cfg.get("min_discount_percent", 25))
    min_cluster = int(cfg.get("min_cluster_size", 3))
    history_days = int(cfg.get("history_days", 30))

    # Group current items by cluster
    by_cluster: dict[str, list[NormalizedListing]] = defaultdict(list)
    for item in items:
        if item.is_likely_scam:
            continue
        if item.listing.price_dzd is None or item.listing.price_dzd <= 0:
            continue
        by_cluster[item.cluster_key].append(item)

    opportunities: list[Opportunity] = []

    for cluster_key, cluster_items in by_cluster.items():
        prices = [it.listing.price_dzd for it in cluster_items if it.listing.price_dzd]
        # Augment with historical prices from the DB
        prices += db.cluster_prices(cluster_key, history_days=history_days)
        # Drop obvious outliers (e.g. typo'd 1 DZD)
        prices = [p for p in prices if p > 50]
        if len(prices) < min_cluster:
            continue
        median = statistics.median(prices)
        if median <= 0:
            continue
        for item in cluster_items:
            price = item.listing.price_dzd
            if price is None or price <= 0:
                continue
            discount = (median - price) / median * 100.0
            if discount < min_discount:
                continue
            # Composite ranking score: discount weight × log(sample size)
            import math
            score = discount * (1 + 0.4 * math.log10(max(1, len(prices))))
            opportunities.append(
                Opportunity(
                    listing=item,
                    median_price_dzd=median,
                    discount_percent=discount,
                    sample_size=len(prices),
                    rank_score=score,
                )
            )

    opportunities.sort(key=lambda o: o.rank_score, reverse=True)
    return opportunities
