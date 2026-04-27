"""Soukalys.com scraper — Algerian marketplace with public product listings."""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from souk_dz.config import get_settings
from souk_dz.models import Listing, SourceType
from souk_dz.scrapers.base import (
    BaseScraper,
    detect_wilaya,
    http_client,
    parse_price_dzd,
    polite_sleep,
)

log = logging.getLogger(__name__)


class SoukalysScraper(BaseScraper):
    name = "soukalys"

    def __init__(self) -> None:
        cfg = get_settings().source_config("soukalys")
        self.enabled: bool = cfg.get("enabled", True)
        self.base_url: str = cfg.get("base_url", "https://soukalys.com").rstrip("/")
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
                        log.warning("soukalys: %s returned %s", url, resp.status_code)
                        continue
                    listings.extend(
                        self._parse(resp.text, url)[: self.max_listings - len(listings)]
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("soukalys: failed to fetch %s: %s", url, exc)
                await polite_sleep()
        return listings

    def _parse(self, html: str, page_url: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        results: list[Listing] = []
        # WooCommerce-style storefront — products are <li class="product"> or
        # similar with an anchor to /product/.
        candidates = soup.select("li.product a.woocommerce-LoopProduct-link, a[href*='/product/']")
        seen_urls: set[str] = set()
        for anchor in candidates:
            href = anchor.get("href") or ""
            if not href:
                continue
            full_url = urljoin(page_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            # Title: prefer <h2> or <h3> inside, otherwise anchor text
            title_node = anchor.find(["h2", "h3"]) or anchor
            title = title_node.get_text(strip=True)[:200]
            if not title:
                continue
            # Price: look for sibling .price or amount inside parent
            parent = anchor.find_parent("li") or anchor.parent
            price_text = None
            if parent:
                price_node = parent.select_one(".price, .amount, span.woocommerce-Price-amount")
                if price_node:
                    price_text = price_node.get_text(" ", strip=True)
            results.append(
                Listing(
                    source=SourceType.SOUKALYS,
                    source_label="Soukalys",
                    external_id=full_url.rstrip("/").split("/")[-1] or full_url,
                    title=title,
                    price_raw=price_text,
                    price_dzd=parse_price_dzd(price_text),
                    wilaya=detect_wilaya(title),
                    category_hint="marketplace",
                    url=full_url,
                )
            )
        return results
