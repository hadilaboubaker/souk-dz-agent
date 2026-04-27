"""Lightweight tests that don't hit the network."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from souk_dz.analysis.database import ListingsDB
from souk_dz.analysis.opportunity import find_opportunities
from souk_dz.models import Listing, NormalizedListing, SourceType
from souk_dz.scrapers.base import detect_wilaya, parse_price_dzd


def test_parse_price_basic():
    assert parse_price_dzd("12 000 DA") == 12000.0
    assert parse_price_dzd("12,000 DA") == 12000.0
    assert parse_price_dzd("3500 دج") == 3500.0
    assert parse_price_dzd("1.5 million") == 1_500_000.0
    assert parse_price_dzd("Inbox للسعر") is None
    assert parse_price_dzd(None) is None
    assert parse_price_dzd("") is None


def test_detect_wilaya():
    assert detect_wilaya("for sale in Alger") == "Alger"
    assert detect_wilaya("للبيع في وهران") == "وهران".title()
    assert detect_wilaya("hello world") is None


def _make_listing(**kwargs) -> Listing:
    defaults = dict(
        source=SourceType.OUEDKNISS,
        source_label="Test",
        external_id=str(kwargs.get("external_id", "id")),
        title="iPhone 13 64GB",
        price_dzd=10_000.0,
        scraped_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Listing(**defaults)


def _make_normalized(price: float, ext_id: str = "x", cluster: str = "iphone-13-64gb") -> NormalizedListing:
    return NormalizedListing(
        listing=_make_listing(price_dzd=price, external_id=ext_id),
        canonical_name="iPhone 13",
        category="telephone",
        cluster_key=cluster,
    )


def test_opportunity_detection():
    items = [
        _make_normalized(120_000, "a"),
        _make_normalized(115_000, "b"),
        _make_normalized(125_000, "c"),
        _make_normalized(70_000, "cheap"),  # 41% below median 119k -> opportunity
    ]
    with TemporaryDirectory() as tmp:
        db = ListingsDB(Path(tmp) / "test.db")
        db.upsert(items)
        opps = find_opportunities(items, db)
        assert opps, "expected at least one opportunity"
        assert opps[0].listing.listing.external_id == "cheap"
        assert opps[0].discount_percent > 25
