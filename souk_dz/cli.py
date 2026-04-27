"""Command-line entry point.

Usage:
    souk-dz run            # full daily pipeline
    souk-dz run --dry-run  # don't send email
    souk-dz check          # validate configuration & credentials
    souk-dz scrape SOURCE  # run a single scraper for debugging
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from souk_dz.config import get_settings
from souk_dz.orchestrator import run_pipeline
from souk_dz.scrapers import all_scrapers

app = typer.Typer(help="Souk-DZ price-arbitrage agent")
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True, show_path=False)],
    )


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't send email."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the full daily pipeline."""
    _setup_logging(verbose)
    if dry_run:
        os.environ["DRY_RUN"] = "true"
        # reload settings cache
        from souk_dz import config as _cfg
        _cfg._settings = None  # type: ignore[attr-defined]
    result = asyncio.run(run_pipeline())
    console.print_json(data=result)


@app.command()
def check() -> None:
    """Validate that secrets, config, and dependencies are wired up correctly."""
    _setup_logging()
    settings = get_settings()
    table = Table(title="Souk-DZ configuration check", show_lines=True)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_row(
        "Gemini API key",
        "[green]ok[/green]" if settings.has_ai_credentials() else "[yellow]missing[/yellow]",
        settings.gemini_model,
    )
    table.add_row(
        "Email credentials",
        "[green]ok[/green]" if settings.has_email_credentials() else "[yellow]missing[/yellow]",
        f"{settings.smtp_host}:{settings.smtp_port} → {settings.email_to or '(EMAIL_TO unset)'}",
    )
    enabled = []
    for key in ("ouedkniss", "zerbote", "soukalys", "prixalgerie", "facebook", "tiktok"):
        if settings.source_config(key).get("enabled"):
            enabled.append(key)
    table.add_row("Enabled sources", "[green]%d[/green]" % len(enabled), ", ".join(enabled))
    table.add_row("DB path", "ok", str(settings.db_path))
    console.print(table)


@app.command()
def scrape(
    source: str = typer.Argument(..., help="ouedkniss | zerbote | soukalys | prixalgerie | facebook | tiktok"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run a single scraper and print the results to stdout (debug)."""
    _setup_logging(verbose)
    by_name = {scraper.name: scraper for scraper in all_scrapers()}
    if source not in by_name:
        raise typer.BadParameter(f"unknown source '{source}'. options: {', '.join(by_name)}")
    items = asyncio.run(by_name[source].safe_fetch())
    out = [item.model_dump(mode="json") for item in items]
    console.print(f"[bold]{source}[/bold]: {len(items)} listings")
    console.print(json.dumps(out[:5], ensure_ascii=False, indent=2))
    console.print(f"... (showing 5 of {len(items)})")


if __name__ == "__main__":
    app()
