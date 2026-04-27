"""Facebook public pages / public groups scraper.

We use Playwright headless to load the public mbasic / m.facebook.com URL of each
configured Page or Group. Only publicly visible posts are read. No interaction,
no login, no automation of user actions — read-only.

⚠️ Limits:
  - Facebook may rate-limit aggressive scraping. We sleep between requests and
    cap the number of posts per source. Use a dedicated browser identity.
  - Many Algerian sellers write "Inbox" or "MP" instead of a number, so the
    price-extraction success rate here is naturally lower than for classifieds.
"""
from __future__ import annotations

import logging
import re
from typing import Any

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


def _to_mbasic(url: str) -> str:
    """Translate an www.facebook.com URL into an mbasic.facebook.com URL.

    mbasic returns a no-JS HTML page that is dramatically easier to parse and
    less likely to require login than the SPA version.
    """
    return re.sub(r"https?://(www\.|m\.)?facebook\.com", "https://mbasic.facebook.com", url)


class FacebookScraper(BaseScraper):
    name = "facebook"

    def __init__(self) -> None:
        cfg = get_settings().source_config("facebook")
        self.enabled: bool = cfg.get("enabled", True)
        self.pages: list[dict[str, Any]] = cfg.get("pages", []) or []
        self.groups: list[dict[str, Any]] = cfg.get("groups", []) or []
        self.posts_per_source: int = int(cfg.get("posts_per_source", 10))
        self.max_listings = get_settings().max_listings_per_source

    async def fetch(self) -> list[Listing]:
        if not self.enabled:
            return []
        results: list[Listing] = []
        sources = [
            (entry, SourceType.FACEBOOK_PAGE) for entry in self.pages
        ] + [
            (entry, SourceType.FACEBOOK_GROUP) for entry in self.groups
        ]
        if not sources:
            return []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            try:
                context = await browser.new_context(user_agent=USER_AGENT, locale="fr-FR")
                page = await context.new_page()
                for entry, source_type in sources:
                    if len(results) >= self.max_listings:
                        break
                    url = _to_mbasic(entry.get("url", ""))
                    name = entry.get("name", url)
                    if not url:
                        continue
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("facebook: timeout on %s: %s", url, exc)
                        continue
                    if "login" in page.url and "mbasic" in page.url:
                        log.warning("facebook: %s requires login (skipping)", url)
                        continue
                    posts = await page.query_selector_all("div[role='article'], div._55wo, article")
                    if not posts:
                        # mbasic uses div with id starting by "u_..."
                        posts = await page.query_selector_all("div[id^='u_']")
                    count = 0
                    for post in posts:
                        if count >= self.posts_per_source or len(results) >= self.max_listings:
                            break
                        try:
                            text = (await post.inner_text()).strip()
                        except Exception:
                            continue
                        if not text or len(text) < 20:
                            continue
                        title = text.splitlines()[0][:200]
                        price_raw = next(
                            (
                                line
                                for line in text.splitlines()
                                if re.search(r"\d", line)
                                and any(t in line for t in ("DA", "دج", "دينار", "Da", "da"))
                            ),
                            None,
                        )
                        external_id = f"{name}::{hash(text) & 0xFFFFFFFF:x}"
                        results.append(
                            Listing(
                                source=source_type,
                                source_label=f"Facebook / {name}",
                                external_id=external_id,
                                title=title,
                                description=text[:600],
                                price_raw=price_raw,
                                price_dzd=parse_price_dzd(price_raw),
                                wilaya=detect_wilaya(text),
                                url=url,
                            )
                        )
                        count += 1
                    await polite_sleep(2.0, 4.0)
            finally:
                await browser.close()
        return results
