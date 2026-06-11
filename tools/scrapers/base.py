"""Base scraper classes used by every country-specific scraper.

Two kinds:
- ``PlaywrightScraper``: opens a real Chromium, lets the page render JS, then
  reads values via locators. Use for SPAs (Farmtal, Arla, Danish Crown).
- ``ApiScraper``: pure urllib/HTTP — no browser. Use for clean APIs
  (Nationalbanken FX XML, exchangerate.host, etc.).

Each subclass implements ``scrape()`` and returns a dict
``{indicator_key: indicator_dict}`` or empty dict if everything failed.

An indicator_dict has the canonical shape consumed by the frontend:
    {"key": "hvede", "icon": "hvede", "name": "Brødhvede",
     "value": 152.3, "value_display": "152,30 DKK/hkg", "unit": "DKK/hkg",
     "date": "2026-06-11", "source_url": "https://...",
     "source_name": "SEGES Farmtal Online", "stale": False}
"""
from __future__ import annotations

import datetime as _dt
import logging
import socket
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("scrapers")

# Module-level toggle: tests / dry runs set this to False to skip browser launch.
PLAYWRIGHT_ENABLED = True

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 landbrugstal-noteringer/2.0 "
    "(+https://landbrugstal.dk)"
)

DEFAULT_TIMEOUT_MS = 30_000   # 30s per page action
DEFAULT_HTTP_TIMEOUT = 20     # 20s for urllib


def today_iso() -> str:
    return _dt.date.today().isoformat()


def now_iso_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_dk_number(value: float | None, unit: str) -> str:
    """Render a value in da-DK style (comma decimal) with the unit suffix."""
    if value is None:
        return "—"
    if abs(value) >= 1000:
        s = "{0:,.2f}".format(value).replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        s = "{0:.2f}".format(value).replace(".", ",")
    return "{0} {1}".format(s, unit).strip()


class Scraper:
    """Abstract base. Concrete classes set name + source_url + source_name."""

    name: str = "base"
    source_url: str = ""
    source_name: str = ""

    def scrape(self) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    def safe_run(self) -> dict[str, dict[str, Any]]:
        """Wrap scrape() so one failing source never breaks the rest."""
        try:
            out = self.scrape()
            log.info("[%s] %d indicator(s)", self.name, len(out))
            return out or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] failed: %s: %s", self.name, type(exc).__name__, exc)
            return {}


class ApiScraper(Scraper):
    """For sources that return plain text/JSON/XML — no browser needed."""

    timeout = DEFAULT_HTTP_TIMEOUT

    def http_get(self, url: str | None = None, headers: dict | None = None) -> str | None:
        url = url or self.source_url
        req = urllib.request.Request(url, headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "da-DK,da;q=0.9,en;q=0.6",
            **(headers or {}),
        })
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                raw = resp.read()
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("latin-1", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as exc:
            log.warning("[%s] http_get failed: %s", self.name, exc)
            return None


class PlaywrightScraper(Scraper):
    """Renders the page in headless Chromium so JS-driven content is available.

    Subclasses override ``extract(page) -> dict``. The base run loop deals
    with browser lifecycle, default timeouts and locale.
    """

    locale: str = "da-DK"
    timezone_id: str = "Europe/Copenhagen"
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    wait_until: str = "networkidle"
    extra_wait_ms: int = 800  # small pause after networkidle for any final JS

    def extract(self, page) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    def scrape(self) -> dict[str, dict[str, Any]]:
        if not PLAYWRIGHT_ENABLED:
            log.info("[%s] playwright disabled — skipping", self.name)
            return {}
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("[%s] playwright not installed — pip install playwright && playwright install chromium", self.name)
            return {}
        out: dict[str, dict[str, Any]] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                locale=self.locale,
                timezone_id=self.timezone_id,
                viewport={"width": 1366, "height": 900},
            )
            page = ctx.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                page.goto(self.source_url, wait_until=self.wait_until)
                if self.extra_wait_ms:
                    page.wait_for_timeout(self.extra_wait_ms)
                out = self.extract(page) or {}
            finally:
                ctx.close()
                browser.close()
        return out


def parse_dk_number(text: str | None) -> float | None:
    """Parse a number that may be DK-formatted (1.234,56 / 152,5) or US (152.3)."""
    if text is None:
        return None
    import re
    m = re.search(r"[-+]?\d[\d.,\s]*", str(text))
    if not m:
        return None
    raw = m.group(0).replace("\xa0", "").replace(" ", "").strip()
    has_comma = "," in raw
    has_dot = "." in raw
    if has_comma and has_dot:
        # Whichever appears LATER is the decimal separator.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif has_comma:
        raw = raw.replace(",", ".")
    elif has_dot:
        # Treat trailing ".XXX" (exactly 3 digits) as thousands ONLY if the
        # number is plausibly 4+ digit integer (else it's a decimal).
        before, _, after = raw.partition(".")
        if len(after) == 3 and len(before) >= 4 and before.lstrip("-+").isdigit():
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None
