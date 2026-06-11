"""Nationalbanken — daily EUR/DKK and USD/DKK rates.

Pure XML feed (no JS), so this is an ApiScraper, not Playwright.
Format: <currency code="EUR" desc="Euro" rate="747.43"/>
Rate is "DKK per 100 units" -> divide by 100 for the per-1 rate we display.
"""
from __future__ import annotations
import re
from typing import Any
from .base import ApiScraper, today_iso, format_dk_number


class NationalbankenFX(ApiScraper):
    name = "nationalbanken_fx"
    source_url = "https://www.nationalbanken.dk/api/currencyratesxml?lang=en"
    source_name = "Nationalbanken"

    def scrape(self) -> dict[str, dict[str, Any]]:
        body = self.http_get()
        if not body:
            return {}
        rates: dict[str, float] = {}
        for m in re.finditer(r'code="([A-Z]{3})"[^>]*?\brate="([\d.,]+)"', body):
            try:
                rates[m.group(1)] = float(m.group(2)) / 100.0
            except ValueError:
                pass
        out: dict[str, dict[str, Any]] = {}
        if "EUR" in rates:
            out["eur_dkk"] = {
                "key": "eur_dkk",
                "icon": "eur_dkk",
                "name": "EUR/DKK",
                "value": rates["EUR"],
                "value_display": format_dk_number(rates["EUR"], "DKK") + " (per 1 EUR)",
                "unit": "DKK",
                "date": today_iso(),
                "source_url": "https://www.nationalbanken.dk/",
                "source_name": self.source_name,
                "stale": False,
            }
        if "USD" in rates:
            out["usd_dkk"] = {
                "key": "usd_dkk",
                "icon": "usd_dkk",
                "name": "USD/DKK",
                "value": rates["USD"],
                "value_display": format_dk_number(rates["USD"], "DKK") + " (per 1 USD)",
                "unit": "DKK",
                "date": today_iso(),
                "source_url": "https://www.nationalbanken.dk/",
                "source_name": self.source_name,
                "stale": False,
            }
        return out
