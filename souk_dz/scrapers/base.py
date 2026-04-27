"""Common scraper utilities: price parsing, HTTP/Playwright helpers, base class."""
from __future__ import annotations

import asyncio
import logging
import random
import re
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from souk_dz.models import Listing

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Algerian wilaya names (Arabic + French) for crude detection in scraped text
WILAYAS = {
    "alger", "algiers", "الجزائر", "oran", "وهران", "constantine", "قسنطينة",
    "annaba", "عنابة", "blida", "البليدة", "setif", "سطيف", "tlemcen", "تلمسان",
    "batna", "باتنة", "djelfa", "الجلفة", "biskra", "بسكرة", "ghardaia", "غرداية",
    "tizi ouzou", "تيزي وزو", "bejaia", "بجاية", "skikda", "سكيكدة", "mostaganem",
    "مستغانم", "bordj bou arreridj", "برج بوعريريج", "bouira", "البويرة",
    "msila", "المسيلة", "ouargla", "ورقلة", "ain defla", "عين الدفلى",
}

# Currency tokens we accept after a price number
_CURRENCY = r"(?:DA|دج|د\.ج|دينار|دج\.|da)"

_PRICE_PATTERNS = [
    # number followed by currency: e.g. 12 000 DA, 12,000 DA, 15.500,00 د.ج, 3500 دج
    re.compile(rf"(\d[\d\s\u00a0.,]{{2,15}}\d|\d{{3,9}})\s*{_CURRENCY}", re.IGNORECASE),
    # currency followed by number: د.ج 15.500,00
    re.compile(rf"{_CURRENCY}\s*(\d[\d\s\u00a0.,]{{2,15}}\d|\d{{3,9}})", re.IGNORECASE),
    # 1.5 million / 2 milliard / 3 مليون
    re.compile(r"(\d+(?:[.,]\d+)?)\s*(million|milliard|مليون|مليار)", re.IGNORECASE),
]


def _euro_to_float(s: str) -> float | None:
    """Parse '15.500,00' (European fmt) or '15,500.00' (US fmt) -> 15500.00."""
    s = s.strip().replace("\u00a0", " ").replace(" ", "")
    if "," in s and "." in s:
        # last separator wins as decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # If only one comma and 1-2 digits after -> decimal; else thousands sep
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            s = f"{parts[0]}.{parts[1]}"
        else:
            s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_price_dzd(raw: str | None) -> float | None:
    """Best-effort parse of an Algerian price string into DZD float.

    Handles spaces/commas/dots as thousand separators, "million" / "مليون"
    suffixes, currency before or after the number, etc. Returns ``None`` if
    no number can be extracted.
    """
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    s_low = s.lower()

    for idx, pattern in enumerate(_PRICE_PATTERNS):
        match = pattern.search(s)
        if not match:
            continue
        if idx == 2:  # million / milliard
            try:
                value = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            unit = match.group(2).lower()
            if unit in ("million", "مليون"):
                value *= 1_000_000
            else:
                value *= 1_000_000_000
        else:
            value = _euro_to_float(match.group(1))
            if value is None:
                continue
        if 100 <= value <= 1_000_000_000_000:
            return value

    if any(token in s_low for token in ("inbox", "mp ", "اتصل", "contact", "prix négo")) and not re.search(r"\d{4,}", s):
        return None
    return None


def detect_wilaya(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    for w in WILAYAS:
        if w in low:
            return w.title()
    return None


@asynccontextmanager
async def http_client(**kwargs) -> AsyncIterator[httpx.AsyncClient]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,ar;q=0.8,en;q=0.7",
    }
    headers.update(kwargs.pop("headers", {}))
    async with httpx.AsyncClient(
        headers=headers, timeout=30.0, follow_redirects=True, http2=False, **kwargs
    ) as client:
        yield client


async def polite_sleep(min_s: float = 0.6, max_s: float = 1.6) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


class BaseScraper(ABC):
    """Each scraper implements ``fetch()`` returning a list of Listing objects."""

    name: str

    @abstractmethod
    async def fetch(self) -> list[Listing]:
        """Return up to ``settings.max_listings_per_source`` listings."""

    async def safe_fetch(self) -> list[Listing]:
        try:
            results = await self.fetch()
            log.info("[%s] collected %d listings", self.name, len(results))
            return results
        except Exception as exc:  # noqa: BLE001 — keep one bad source from killing the whole pipeline
            log.warning("[%s] failed: %s", self.name, exc)
            return []
