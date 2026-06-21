"""SEGES Farmtal Online — hvede / byg / raps / majs spot.

Farmtal is a JSP app with a clickable navigation tree. The simplest robust
path is the public "Korn og foder" page which shows weekly notering for
the major grain qualities. We don't navigate — we go straight to the
"Notering for korn" public report URL.

If that view changes shape, the scrape returns empty and the indicator falls
back to "Se kilde →" in the UI (handled by js/noteringer-dk.js).

DEBUGGING: when no values are matched (e.g. SEGES changed the page layout),
the scraper saves the rendered body text to data/_debug_farmtal_<date>.txt
so the next failure is diagnosable from the workflow artifacts without
needing to reproduce the network conditions locally.
"""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Any
from .base import PlaywrightScraper, today_iso, format_dk_number, parse_dk_number

log = logging.getLogger("scrapers")


# Targets: tuple per grain.
#   labels: ordered list of label variants to try (first match wins).
#           SEGES sometimes renames "Brødhvede" -> "Hvede, brød" etc.
#   key:    output dict key (frontend / data file convention).
#   unit:   display unit on cards.
GRAIN_TARGETS = [
    {
        "labels": ["Brødhvede", "Brød-hvede", "Brod-hvede", "Hvede, brød", "Hvede brod"],
        "key": "hvede",
        "unit": "DKK/hkg",
    },
    {
        "labels": ["Foderbyg", "Foder-byg", "Byg, foder", "Foderbyg, vinter"],
        "key": "byg",
        "unit": "DKK/hkg",
    },
    {
        "labels": ["Industriraps", "Raps, industri", "Raps industri", "Vinterraps"],
        "key": "raps",
        "unit": "DKK/hkg",
    },
    {
        "labels": ["Foderhvede", "Foder-hvede", "Hvede, foder"],
        "key": "majs",  # majs not on Farmtal — use foderhvede as proxy
        "unit": "DKK/hkg",
    },
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
        for sel in [
            "text=Accepter alle",
            "text=Acceptér alle",
            "text=Tillad alle",
            "text=Accept all",
            "button:has-text('OK')",
            "button:has-text('Accepter')",
            "[id*='cookie'] button",
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=600):
                    btn.click(timeout=1500)
                    page.wait_for_timeout(400)
            except Exception:
                pass

        # Try to wait for the data table to appear before extracting.
        # The JSP renders a <table> with notering data; if it's missing the
        # page never finished loading the actual report frame.
        try:
            page.wait_for_selector("table, [class*='notering'], [id*='Notering']", timeout=8_000)
        except Exception:
            pass

        body = page.locator("body").inner_text()
        out: dict[str, dict[str, Any]] = {}

        for target in GRAIN_TARGETS:
            value = None
            matched_label = None
            for label in target["labels"]:
                # "<label> ... 165,40" (any small gap, up to 200 chars now)
                m = re.search(
                    rf"{re.escape(label)}[\s\S]{{0,200}}?(\d{{2,3}}[.,]\d{{1,2}})",
                    body, re.IGNORECASE,
                )
                if not m:
                    continue
                v = parse_dk_number(m.group(1))
                if v is None or v < 50 or v > 800:  # sanity range for DKK/hkg grain
                    continue
                value = v
                matched_label = label
                break

            if value is None:
                continue

            out[target["key"]] = {
                "key": target["key"],
                "icon": target["key"],
                "name": matched_label,
                "value": value,
                "value_display": format_dk_number(value, target["unit"]),
                "unit": target["unit"],
                "date": today_iso(),
                "source_url": self.source_url,
                "source_name": self.source_name,
                "stale": False,
            }

        # If we got nothing (or fewer than half the targets), dump the rendered
        # body text so the next debugging session does not have to reproduce
        # the JSP locally. Goes to data/_debug_farmtal_<date>.txt — uploaded
        # as part of the regular commit if the workflow opts to keep it.
        if len(out) < len(GRAIN_TARGETS) / 2:
            try:
                debug_dir = Path(__file__).resolve().parents[2] / "data"
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_path = debug_dir / f"_debug_farmtal_{today_iso()}.txt"
                debug_path.write_text(
                    f"=== farmtal_seges debug dump {today_iso()} ===\n"
                    f"matched: {sorted(out.keys())}\n"
                    f"missing: {[t['key'] for t in GRAIN_TARGETS if t['key'] not in out]}\n"
                    f"--- body.inner_text() (first 8000 chars) ---\n"
                    + body[:8000],
                    encoding="utf-8",
                )
                log.warning(
                    "[%s] only matched %d/%d targets — dumped body to %s",
                    self.name, len(out), len(GRAIN_TARGETS), debug_path.name,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] failed to dump debug body: %s", self.name, e)

        return out
