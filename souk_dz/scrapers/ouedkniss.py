"""Ouedkniss.com scraper.

Ouedkniss is an SPA powered by a private GraphQL API at https://api.ouedkniss.com/graphql.
Rather than reverse-engineering the (unstable) GraphQL schema, we render the public
listing pages with Playwright headless Chromium and parse the rendered DOM. This is
slower but resilient against API changes and is what the ouedkniss-scraper community
projects do today.
"""
from __future__ import annotations

import logging
import re

from playwright.async_api import async_playwright

from souk_dz.config import get_settings
from souk_dz.models import Listing, SourceType
from souk_dz.scrapers.base import (
    USER_AGENT,
    BaseScraper,
    detect_wilaya,
    parse_price_dzd,
    polite_sleep,
)

log = logging.getLogger(__name__)

BASE_URL = "https://www.ouedkniss.com"


class OuedknissScraper(BaseScraper):
    name = "ouedkniss"

    def __init__(self) -> None:
        cfg = get_settings().source_config("ouedkniss")
        self.enabled: bool = cfg.get("enabled", True)
        self.categories: list[str] = cfg.get("categories", []) or []
        self.pages_per_category: int = int(cfg.get("pages_per_category", 1))
        self.wilaya_filter: str | None = cfg.get("wilaya_filter")
        self.max_listings = get_settings().max_listings_per_source

    def _build_url(self, category: str, page: int) -> str:
        url = f"{BASE_URL}/s/{category}?page={page}"
        if self.wilaya_filter:
            url += f"&regions={self.wilaya_filter}"
        return url

    async def fetch(self) -> list[Listing]:
        if not self.enabled or not self.categories:
            return []

        listings: list[Listing] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            try:
                context = await browser.new_context(user_agent=USER_AGENT, locale="fr-DZ")
                page = await context.new_page()
                for category in self.categories:
                    if len(listings) >= self.max_listings:
                        break
                    for page_num in range(1, self.pages_per_category + 1):
                        if len(listings) >= self.max_listings:
                            break
                        url = self._build_url(category, page_num)
                        log.debug("ouedkniss: fetching %s", url)
                        try:
                            await page.goto(url, wait_until="networkidle", timeout=45_000)
                        except Exception as exc:  # noqa: BLE001
                            log.warning("ouedkniss: timeout on %s: %s", url, exc)
                            continue
                        # Listings are rendered as <a class="ok-card"> or similar
                        cards = await page.query_selector_all(
                            "a[href*='/'][class*='card'], div[class*='announcement-card']"
                        )
                        if not cards:
                            # Fallback: any anchor that looks like an annonce link
                            cards = await page.query_selector_all("a[href*='/annonces/']")
                        seen_urls: set[str] = set()
                        for card in cards:
                            try:
                                href = await card.get_attribute("href") or ""
                                if not href or "annonces" not in href and "/d/" not in href:
                                    continue
                                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                                if full_url in seen_urls:
                                    continue
                                seen_urls.add(full_url)

                                text = (await card.inner_text()).strip()
                                if not text:
                                    continue
                                lines = [line.strip() for line in text.splitlines() if line.strip()]
                                title = lines[0][:200] if lines else "(sans titre)"
                                price_raw = next(
                                    (
                                        line
                                        for line in lines
                                        if re.search(r"\d", line)
                                        and ("DA" in line or "دج" in line or "Million" in line.lower())
                                    ),
                                    None,
                                )
                                wilaya = detect_wilaya(text)
                                external_id = full_url.rstrip("/").split("/")[-1]
                                listings.append(
                                    Listing(
                                        source=SourceType.OUEDKNISS,
                                        source_label=f"Ouedkniss / {category}",
                                        external_id=external_id,
                                        title=title,
                                        description=text[:500],
                                        price_raw=price_raw,
                                        price_dzd=parse_price_dzd(price_raw),
                                        wilaya=wilaya,
                                        category_hint=category,
                                        url=full_url,
                                    )
                                )
                                if len(listings) >= self.max_listings:
                                    break
                            except Exception as exc:  # noqa: BLE001
                                log.debug("ouedkniss: skipped a card: %s", exc)
                                continue
                        await polite_sleep(1.5, 3.0)
            finally:
                await browser.close()
        return listings
