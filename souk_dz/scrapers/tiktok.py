"""TikTok scraper — by hashtag and by account.

TikTok aggressively blocks scrapers, so this is a best-effort implementation:
it loads ``https://www.tiktok.com/tag/<hashtag>`` and ``/@<user>`` pages with
Playwright and extracts the JSON state embedded in <script id="SIGI_STATE">.

Many runs may fail because of TikTok's bot detection. The pipeline is designed
so that an empty TikTok output does not break the daily report.
"""
from __future__ import annotations

import json
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


class TikTokScraper(BaseScraper):
    name = "tiktok"

    def __init__(self) -> None:
        cfg = get_settings().source_config("tiktok")
        self.enabled: bool = cfg.get("enabled", True)
        self.hashtags: list[str] = cfg.get("hashtags", []) or []
        self.accounts: list[str] = cfg.get("accounts", []) or []
        self.videos_per_source: int = int(cfg.get("videos_per_source", 10))
        self.max_listings = get_settings().max_listings_per_source

    async def fetch(self) -> list[Listing]:
        if not self.enabled or (not self.hashtags and not self.accounts):
            return []
        results: list[Listing] = []
        urls: list[tuple[str, str]] = []
        for tag in self.hashtags:
            urls.append((f"https://www.tiktok.com/tag/{tag.lstrip('#')}", f"#{tag}"))
        for account in self.accounts:
            urls.append((f"https://www.tiktok.com/@{account.lstrip('@')}", f"@{account}"))

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            try:
                context = await browser.new_context(user_agent=USER_AGENT, locale="fr-FR")
                page = await context.new_page()
                for url, label in urls:
                    if len(results) >= self.max_listings:
                        break
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("tiktok: failed %s: %s", url, exc)
                        continue
                    html = await page.content()
                    new = self._parse(html, label)[: self.videos_per_source]
                    results.extend(new[: self.max_listings - len(results)])
                    await polite_sleep(2.0, 4.0)
            finally:
                await browser.close()
        return results

    def _parse(self, html: str, label: str) -> list[Listing]:
        # SIGI_STATE / __UNIVERSAL_DATA_FOR_REHYDRATION__ vary by TikTok build
        json_blob: str | None = None
        for needle in ("__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE"):
            match = re.search(
                rf'<script[^>]*id="{needle}"[^>]*>(.+?)</script>', html, re.S
            )
            if match:
                json_blob = match.group(1)
                break
        if not json_blob:
            return []
        try:
            data = json.loads(json_blob)
        except json.JSONDecodeError:
            return []

        # Walk the tree and pull every dict that looks like a video item.
        videos: list[dict] = []

        def walk(node):
            if isinstance(node, dict):
                if "desc" in node and ("video" in node or "stats" in node or "playAddr" in node):
                    videos.append(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(data)
        out: list[Listing] = []
        seen: set[str] = set()
        for video in videos:
            vid = str(video.get("id") or video.get("aweme_id") or "")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            desc = (video.get("desc") or "").strip()
            if not desc:
                continue
            author = (
                (video.get("author") or {}).get("uniqueId")
                if isinstance(video.get("author"), dict)
                else video.get("author")
            ) or "unknown"
            url = f"https://www.tiktok.com/@{author}/video/{vid}"
            price_raw = next(
                (
                    line
                    for line in desc.splitlines()
                    if re.search(r"\d", line)
                    and any(t in line for t in ("DA", "دج", "دينار", "da"))
                ),
                None,
            )
            out.append(
                Listing(
                    source=SourceType.TIKTOK,
                    source_label=f"TikTok / {label}",
                    external_id=vid,
                    title=desc.splitlines()[0][:200],
                    description=desc[:600],
                    price_raw=price_raw,
                    price_dzd=parse_price_dzd(price_raw),
                    wilaya=detect_wilaya(desc),
                    contact=author,
                    url=url,
                )
            )
        return out
