"""Use Google Gemini (free tier) to normalize raw listings into structured records.

The normalizer:
  * extracts a canonical product name in Arabic and French,
  * picks a high-level category (electronique / mode / maison / ...),
  * detects brand + new/used flag + obvious-scam flag,
  * computes a stable cluster key for price comparison.

If no Gemini API key is configured, we fall back to a simple heuristic
normalizer so the rest of the pipeline still works (with reduced quality).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from souk_dz.config import get_settings
from souk_dz.models import Listing, NormalizedListing

log = logging.getLogger(__name__)

CANONICAL_CATEGORIES = [
    "electronique", "telephone", "informatique", "mode", "beaute",
    "maison", "sport", "auto", "enfants", "alimentation", "autre",
]

PROMPT = """You are an expert e-commerce data normalizer for the Algerian market.

Given the following raw classified-ad listings (titles + descriptions in Arabic,
Algerian Darija, French and Franco-arabe), produce a JSON array where each
item corresponds to the input listing at the same index. Return STRICT JSON only,
no commentary.

Each output item must contain these fields:
  - "canonical_name"     (string, in Arabic) — the standardized product name
  - "canonical_name_fr"  (string, in French)
  - "category"           (string, one of: {categories})
  - "sub_category"       (string or null)
  - "brand"              (string or null)
  - "is_used"            (boolean or null) — true if the listing says مستعمل / occasion
  - "is_likely_scam"     (boolean) — true for vague "investment opportunities", "Western Union", etc.
  - "cluster_key"        (string, ASCII slug under 64 chars) — items that refer to the SAME product
                          must share the SAME cluster_key. Build it from canonical_name_fr +
                          brand + storage/size if relevant.

Listings to normalize (one per line, JSON):
{listings_json}
"""


def _heuristic_normalize(listing: Listing) -> NormalizedListing:
    """Cheap fallback if the LLM is not available."""
    title = listing.title.strip()
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:64].strip("-") or "unknown"
    return NormalizedListing(
        listing=listing,
        canonical_name=title[:120],
        canonical_name_fr=title[:120],
        category="autre",
        sub_category=listing.category_hint,
        brand=None,
        is_used=None,
        is_likely_scam=False,
        cluster_key=slug,
        confidence=0.3,
    )


def _build_prompt(batch: list[Listing]) -> str:
    rows = []
    for idx, listing in enumerate(batch):
        rows.append(
            json.dumps(
                {
                    "i": idx,
                    "title": listing.title,
                    "desc": (listing.description or "")[:300],
                    "category_hint": listing.category_hint,
                    "price_raw": listing.price_raw,
                },
                ensure_ascii=False,
            )
        )
    return PROMPT.format(
        categories=", ".join(CANONICAL_CATEGORIES),
        listings_json="\n".join(rows),
    )


def _parse_response(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    # Strip markdown fences if Gemini wraps the JSON in ```json ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if isinstance(data, dict) and "items" in data:
        data = data["items"]
    if not isinstance(data, list):
        raise ValueError("LLM did not return a JSON array")
    return data


async def normalize(listings: list[Listing]) -> list[NormalizedListing]:
    if not listings:
        return []
    settings = get_settings()
    if not settings.has_ai_credentials():
        log.warning("normalizer: no GEMINI_API_KEY configured, using heuristic fallback")
        return [_heuristic_normalize(listing) for listing in listings]

    try:
        import google.generativeai as genai
    except ImportError:
        log.warning("google-generativeai not installed; using fallback")
        return [_heuristic_normalize(listing) for listing in listings]

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        settings.gemini_model,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2,
            "max_output_tokens": 8192,
        },
    )

    out: list[NormalizedListing] = []
    BATCH = 20  # Gemini handles ~20 listings per call comfortably
    for start in range(0, len(listings), BATCH):
        batch = listings[start : start + BATCH]
        prompt = _build_prompt(batch)
        try:
            resp = await model.generate_content_async(prompt)
            parsed = _parse_response(resp.text)
        except Exception as exc:  # noqa: BLE001
            log.warning("Gemini call failed (%s); using fallback for this batch", exc)
            out.extend(_heuristic_normalize(item) for item in batch)
            continue

        if len(parsed) != len(batch):
            log.warning(
                "normalizer: model returned %d items for batch of %d, padding",
                len(parsed), len(batch),
            )

        for idx, listing in enumerate(batch):
            row = parsed[idx] if idx < len(parsed) else {}
            try:
                out.append(
                    NormalizedListing(
                        listing=listing,
                        canonical_name=str(row.get("canonical_name") or listing.title)[:200],
                        canonical_name_fr=row.get("canonical_name_fr"),
                        category=str(row.get("category") or "autre")[:40],
                        sub_category=row.get("sub_category"),
                        brand=row.get("brand"),
                        is_used=row.get("is_used"),
                        is_likely_scam=bool(row.get("is_likely_scam", False)),
                        cluster_key=str(row.get("cluster_key") or "unknown")[:64],
                        confidence=0.85,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("normalizer: skipping malformed entry: %s", exc)
                out.append(_heuristic_normalize(listing))
    return out
