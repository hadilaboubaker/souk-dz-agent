"""Core data models passed between scrapers, AI, analysis, and reporting."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceType(str, Enum):
    OUEDKNISS = "ouedkniss"
    ZERBOTE = "zerbote"
    SOUKALYS = "soukalys"
    PRIXALGERIE = "prixalgerie"
    FACEBOOK_PAGE = "facebook_page"
    FACEBOOK_GROUP = "facebook_group"
    TIKTOK = "tiktok"


class Listing(BaseModel):
    """A single product listing pulled from one of the sources."""

    source: SourceType
    source_label: str = Field(description="Human-readable source name, e.g. 'Ouedkniss / Téléphones'")
    external_id: str = Field(description="Stable identifier from the source (URL slug, post id, ...)")
    title: str
    description: Optional[str] = None
    price_dzd: Optional[float] = Field(
        default=None,
        description="Price in Algerian Dinar. None if seller did not publish a price.",
    )
    price_raw: Optional[str] = Field(default=None, description="Original price string as scraped")
    currency: str = "DZD"
    wilaya: Optional[str] = Field(default=None, description="Algerian wilaya / region")
    category_hint: Optional[str] = None
    contact: Optional[str] = Field(default=None, description="Phone / WhatsApp / username")
    url: Optional[HttpUrl] = None
    image_url: Optional[HttpUrl] = None
    posted_at: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=_utcnow)


class NormalizedListing(BaseModel):
    """A Listing enriched by the AI normalizer."""

    listing: Listing
    canonical_name: str = Field(description="Standardized product name (Arabic)")
    canonical_name_fr: Optional[str] = None
    category: str = Field(description="Top-level category, e.g. 'electronique', 'mode', 'maison'")
    sub_category: Optional[str] = None
    brand: Optional[str] = None
    is_used: Optional[bool] = None
    is_likely_scam: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    cluster_key: str = Field(description="Stable key used to cluster identical products")


class Opportunity(BaseModel):
    """A specific listing flagged as below-market price."""

    listing: NormalizedListing
    median_price_dzd: float
    discount_percent: float = Field(description="How far below median (positive %)")
    sample_size: int = Field(description="How many comparable listings were used to compute median")
    rank_score: float = Field(description="Composite score for sorting")
