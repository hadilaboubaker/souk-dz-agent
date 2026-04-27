"""Registry of all scrapers."""
from __future__ import annotations

from souk_dz.scrapers.base import BaseScraper
from souk_dz.scrapers.facebook import FacebookScraper
from souk_dz.scrapers.ouedkniss import OuedknissScraper
from souk_dz.scrapers.prixalgerie import PrixAlgerieScraper
from souk_dz.scrapers.soukalys import SoukalysScraper
from souk_dz.scrapers.tiktok import TikTokScraper
from souk_dz.scrapers.zerbote import ZerboteScraper


def all_scrapers() -> list[BaseScraper]:
    return [
        OuedknissScraper(),
        ZerboteScraper(),
        SoukalysScraper(),
        PrixAlgerieScraper(),
        FacebookScraper(),
        TikTokScraper(),
    ]


__all__ = [
    "BaseScraper",
    "OuedknissScraper",
    "ZerboteScraper",
    "SoukalysScraper",
    "PrixAlgerieScraper",
    "FacebookScraper",
    "TikTokScraper",
    "all_scrapers",
]
