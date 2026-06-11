"""Danish Crown — grisenotering + kreaturnotering.

Both pages are SSR-rendered with a basic Vue/React shell; Chromium settles
the layout reliably. We pick the "basis"-class row for grise
(73-98 kg slaughter weight) and the latest weekly ungtyr R quality for kreatur.
"""
from __future__ import annotations
from typing import Any
from .base import PlaywrightScraper, today_iso, format_dk_number, parse_dk_number


class DanishCrownGris(PlaywrightScraper):
    name = "danishcrown_gris"
    source_url = "https://ejer.danishcrown.com/da-dk/andelsejere/gris/notering/aktuel-grisenotering/"
    source_name = "Danish Crown"

    def extract(self, page) -> dict[str, dict[str, Any]]:
        # Page renders a table. Locate the row containing "73,0-97,9" (basis
        # slaughter-weight band) and grab its first numeric kr/kg cell.
        _dismiss_cookie_banner(page)
        page.wait_for_selector("text=Grisenotering", timeout=20_000)
        # Pull all visible cells around the basis row.
        # The page is essentially a static table; locator inner_text gives the row.
        try:
            row = page.locator("tr,div,p", has_text="73,0-97,9").first
            txt = row.inner_text(timeout=8_000)
        except Exception:
            # Fallback: scan full body.
            txt = page.locator("body").inner_text()
        # Find "73,0-97,9" then take the FIRST decimal number after it.
        import re
        m = re.search(r"73,0[–—-]97,9[\s\S]{0,200}?(\d+[.,]\d+)", txt)
        if not m:
            return {}
        val = parse_dk_number(m.group(1))
        if val is None:
            return {}
        return {
            "grisenotering": {
                "key": "grisenotering",
                "icon": "gris",
                "name": "Grisenotering (basis 73-98 kg)",
                "value": val,
                "value_display": format_dk_number(val, "DKK/kg"),
                "unit": "DKK/kg",
                "date": today_iso(),
                "source_url": self.source_url,
                "source_name": self.source_name,
                "stale": False,
            }
        }


_COOKIE_DISMISS_SELECTORS = (
    "button:has-text('KUN NØDVENDIGE COOKIES')",
    "button:has-text('Kun nødvendige cookies')",
    "button:has-text('OK')",
    "button:has-text('Accepter alle')",
    "button:has-text('Acceptér alle')",
)


def _dismiss_cookie_banner(page) -> None:
    for sel in _COOKIE_DISMISS_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=600):
                btn.click(timeout=1500)
                page.wait_for_timeout(800)
                return
        except Exception:
            continue


class DanishCrownKreatur(PlaywrightScraper):
    name = "danishcrown_kreatur"
    source_url = "https://ejer.danishcrown.com/da-dk/andelsejere/kreatur/notering/aktuel-kreaturnotering/"
    source_name = "Danish Crown"

    def extract(self, page) -> dict[str, dict[str, Any]]:
        _dismiss_cookie_banner(page)
        try:
            page.wait_for_selector("text=Kreaturnotering", timeout=20_000)
        except Exception:
            pass
        try:
            page.wait_for_selector("text=Ungtyr", timeout=8_000)
        except Exception:
            pass
        body = page.locator("main, [role=main], body").first.inner_text()
        import re
        # Look for "Ungtyr" then "R" quality then DKK value (10-50 kr/kg range).
        m = re.search(r"Ungtyr[\s\S]{0,300}?\bR\b[\s\S]{0,200}?(\d{2}[.,]\d{2})", body)
        if not m:
            # Fallback: any 2-digit decimal in the page that plausibly is a
            # kreatur notering (kr/kg roughly 18-45 for current DK market).
            for cand in re.finditer(r"\b(\d{2}[.,]\d{2})\b", body):
                v = parse_dk_number(cand.group(1))
                if v is not None and 18.0 <= v <= 50.0:
                    return _kreatur_dict(self.source_url, self.source_name, v)
            return {}
        v = parse_dk_number(m.group(1))
        if v is None:
            return {}
        return _kreatur_dict(self.source_url, self.source_name, v)


def _kreatur_dict(source_url, source_name, val):
    return {
        "kreaturnotering": {
            "key": "kreaturnotering",
            "icon": "kreatur",
            "name": "Kreaturnotering (Ungtyr R)",
            "value": val,
            "value_display": format_dk_number(val, "DKK/kg"),
            "unit": "DKK/kg",
            "date": today_iso(),
            "source_url": source_url,
            "source_name": source_name,
            "stale": False,
        }
    }
