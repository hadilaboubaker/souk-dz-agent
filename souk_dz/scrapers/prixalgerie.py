"""prixalgerie.com — used as a retail-price baseline reference."""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from souk_dz.config import get_settings
from souk_dz.models import Listing, SourceType
from souk_dz.scrapers.base import (
    BaseScraper,
    http_client,
    parse_price_dzd,
    polite_sleep,
)

log = logging.getLogger(__name__)


class PrixAlgerieScraper(BaseScraper):
    name = "prixalgerie"

    def __init__(self) -> None:
        cfg = get_settings().source_config("prixalgerie")
        self.enabled: bool = cfg.get("enabled", True)
        self.base_url: str = cfg.get("base_url", "https://prixalgerie.com").rstrip("/")
        self.pages: int = int(cfg.get("pages", 1))
        self.max_listings = get_settings().max_listings_per_source

    async def fetch(self) -> list[Listing]:
        if not self.enabled:
            return []
        listings: list[Listing] = []
        async with http_client() as client:
            for page_num in range(1, self.pages + 1):
                if len(listings) >= self.max_listings:
                    break
                url = self.base_url if page_num == 1 else f"{self.base_url}/page/{page_num}/"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    listings.extend(
                        self._parse(resp.text, url)[: self.max_listings - len(listings)]
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("prixalgerie: failed %s: %s", url, exc)
                await polite_sleep()
        return listings

    def _parse(self, html: str, page_url: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        results: list[Listing] = []
        for anchor in soup.select("a[href*='/produit/'], a[href*='/product/'], li.product a"):
            href = anchor.get("href") or ""
            if not href:
                continue
            full_url = urljoin(page_url, href)
            title_node = anchor.find(["h2", "h3"]) or anchor
            title = title_node.get_text(strip=True)[:200]
            if not title:
                continue
            parent = anchor.find_parent("li") or anchor.parent
            price_text = None
            if parent:
                price_node = parent.select_one(".price, .amount")
                if price_node:
                    price_text = price_node.get_text(" ", strip=True)
            results.append(
                Listing(
                    source=SourceType.PRIXALGERIE,
                    source_label="PrixAlgerie (retail reference)",
                    external_id=full_url.rstrip("/").split("/")[-1] or full_url,
                    title=title,
                    price_raw=price_text,
                    price_dzd=parse_price_dzd(price_text),
                    category_hint="retail-reference",
                    url=full_url,
                )
            )
        # dedup
        seen, uniq = set(), []
        for item in results:
            key = str(item.url)
            if key not in seen:
                seen.add(key)
                uniq.append(item)
        return uniq
