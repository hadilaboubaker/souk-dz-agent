"""SMTP email sender (Gmail-compatible) with HTML body + Excel attachment."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from souk_dz.config import get_settings
from souk_dz.models import NormalizedListing, Opportunity

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _render_html(
    *,
    today: str,
    total: int,
    with_price: int,
    clusters: int,
    active_sources: list[str],
    opportunities: list[Opportunity],
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("email.html.j2")
    settings = get_settings()
    return template.render(
        today=today,
        total=total,
        with_price=with_price,
        clusters=clusters,
        active_sources=active_sources,
        opportunities=opportunities,
        min_discount=int(settings.opportunity_config.get("min_discount_percent", 25)),
    )


def send_report(
    *,
    today: str,
    all_items: list[NormalizedListing],
    opportunities: list[Opportunity],
    excel_path: Path,
) -> bool:
    """Send the daily email report. Returns True on success."""
    settings = get_settings()
    if not settings.has_email_credentials():
        log.warning("Email credentials missing — skipping send (DRY).")
        return False

    total = len(all_items)
    with_price = sum(1 for item in all_items if item.listing.price_dzd)
    clusters = len({item.cluster_key for item in all_items})
    active_sources = sorted({item.listing.source_label for item in all_items})

    body_html = _render_html(
        today=today,
        total=total,
        with_price=with_price,
        clusters=clusters,
        active_sources=active_sources,
        opportunities=opportunities[:settings.top_opportunities_count],
    )

    msg = EmailMessage()
    msg["Subject"] = f"📊 سوق-DZ — تقرير {today} — {len(opportunities)} فرصة"
    msg["From"] = settings.email_from
    msg["To"] = settings.email_to
    msg.set_content(
        f"تقرير سوق-DZ ليوم {today}.\n"
        f"تم جمع {total} إعلان، منها {with_price} بسعر معلن.\n"
        f"عدد الفرص المكتشفة: {len(opportunities)}.\n"
        f"تفضل بفتح الإيميل في عميل يدعم HTML للحصول على التقرير الكامل، "
        f"أو افتح ملف Excel المرفق."
    )
    msg.add_alternative(body_html, subtype="html")

    if excel_path.exists():
        with excel_path.open("rb") as fp:
            msg.add_attachment(
                fp.read(),
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=excel_path.name,
            )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        log.info("Email sent to %s", settings.email_to)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("Email send failed: %s", exc)
        return False
