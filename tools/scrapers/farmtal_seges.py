"""SEGES Farmtal Online — hvede / byg / raps / majs spot.

Farmtal is a JSP app with a clickable navigation tree. The simplest robust
path is the public "Korn og foder" page which shows weekly notering for
the major grain qualities. We don't navigate — we go straight to the
"Notering for korn" public report URL.

If that view changes shape, the scrape returns empty and the indicator falls
back to "Se kilde →" in the UI (handled by js/noteringer-dk.js).
"""
from __future__ import annotations
import re
from typing import Any
from .base import PlaywrightScraper, today_iso, format_dk_number, parse_dk_number


# Targets: short name -> (label_for_search_in_page, output_dict_key, unit)
GRAIN_TARGETS = [
    ("Brødhvede",   "hvede", "DKK/hkg"),
    ("Foderbyg",    "byg",   "DKK/hkg"),
    ("Industriraps","raps",  "DKK/hkg"),
    ("Foderhvede",  "majs",  "DKK/hkg"),  # majs not on Farmtal — use foderhvede as proxy for now
]


class FarmtalKorn(PlaywrightScraper):
    name = "farmtal_korn"
    source_url = "https://farmtalonline.dlbr.dk/Navigation/NavigationsMenu.aspx?Bedriftstype=K&Hovedgruppe=A&Element=NoteringerForKorn"
    source_name = "SEGES Farmtal Online"
    timeout_ms = 60_000  # JSP app can be slow on cold start

    def extract(self, page) -> dict[str, dict[str, Any]]:
        try:
            page.wait_for_load_state("networkidle", timeout=40_000)
        except Exception:
            pass

        # Try to dismiss any cookie banner that might cover content.
        for sel in ["text=Accepter alle", "text=Acceptér alle", "text=Tillad alle", "button:has-text('OK')"]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=600):
                    btn.click(timeout=1500)
            except Exception:
                pass

        body = page.locator("body").inner_text()
        out: dict[str, dict[str, Any]] = {}
        for label, key, unit in GRAIN_TARGETS:
            # "Brødhvede ... 165,40" (any small gap)
            m = re.search(
                rf"{re.escape(label)}[\s\S]{{0,160}}?(\d{{2,3}}[.,]\d{{1,2}})",
                body, re.IGNORECASE,
            )
            if not m:
                continue
            v = parse_dk_number(m.group(1))
            if v is None or v < 50 or v > 800:  # sanity range for DKK/hkg grain
                continue
            out[key] = {
                "key": key,
                "icon": key,
                "name": label,
                "value": v,
                "value_display": format_dk_number(v, unit),
                "unit": unit,
                "date": today_iso(),
                "source_url": self.source_url,
                "source_name": self.source_name,
                "stale": False,
            }
        return out
