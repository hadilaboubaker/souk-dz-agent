"""Zerbote.com scraper — static HTML, easy to parse with BeautifulSoup."""
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


class ZerboteScraper(BaseScraper):
    name = "zerbote"

    def __init__(self) -> None:
        cfg = get_settings().source_config("zerbote")
        self.enabled: bool = cfg.get("enabled", True)
        self.base_url: str = cfg.get("base_url", "https://ar.zerbote.com").rstrip("/")
        self.categories: list[str] = cfg.get("categories", []) or []
        self.pages_per_category: int = int(cfg.get("pages_per_category", 1))
        self.max_listings = get_settings().max_listings_per_source

    async def fetch(self) -> list[Listing]:
        if not self.enabled:
            return []
        listings: list[Listing] = []
        async with http_client() as client:
            targets = self.categories or [""]  # empty = home page (latest ads)
            for category in targets:
                if len(listings) >= self.max_listings:
                    break
                for page_num in range(1, self.pages_per_category + 1):
                    if len(listings) >= self.max_listings:
                        break
                    path = f"/{category}" if category else "/"
                    url = f"{self.base_url}{path}"
                    if page_num > 1:
                        url += f"?page={page_num}"
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            log.warning("zerbote: %s returned %s", url, resp.status_code)
                            continue
                        listings.extend(
                            self._parse(resp.text, category or "general", url)[
                                : self.max_listings - len(listings)
                            ]
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.warning("zerbote: failed to fetch %s: %s", url, exc)
                    await polite_sleep()
        return listings

    def _parse(self, html: str, category: str, page_url: str) -> list[Listing]:
        soup = BeautifulSoup(html, "lxml")
        results: list[Listing] = []
        # Zerbote listing cards are typically <a class="card"> wrappers around
        # an image + title + price. We use a permissive selector and filter.
        for card in soup.select("a[href*='/post/'], a[href*='/announce/'], div.card a"):
            href = card.get("href") or ""
            if not href:
                continue
            full_url = urljoin(page_url, href)
            text = card.get_text(separator="\n", strip=True)
            if not text:
                continue
            lines = [line for line in text.splitlines() if line.strip()]
            if not lines:
                continue
            title = lines[0][:200]
            price_raw = next((line for line in lines if any(t in line for t in ("DA", "دج", "دينار"))), None)
            results.append(
                Listing(
                    source=SourceType.ZERBOTE,
                    source_label=f"Zerbote / {category}",
                    external_id=full_url.rstrip("/").split("/")[-1] or full_url,
                    title=title,
                    description=text[:400],
                    price_raw=price_raw,
                    price_dzd=parse_price_dzd(price_raw),
                    wilaya=detect_wilaya(text),
                    category_hint=category,
                    url=full_url,
                )
            )
        # Deduplicate by URL
        seen, uniq = set(), []
        for item in results:
            key = str(item.url)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(item)
        return uniq
