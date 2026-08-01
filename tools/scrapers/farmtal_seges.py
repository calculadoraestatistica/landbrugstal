"""Korn/raps salgspriser — Danmarks Statistik LPRIS10 (Farmtal successor).

History: this scraper originally read the weekly "Noteringer for korn" page
on SEGES Farmtal Online (farmtalonline.dlbr.dk). In June 2026 that page was
removed: the old NavigationsMenu.aspx URL now returns an empty document, the
public navigation tree only exposes monthly DST/L&F statistics that are
frozen ("Statistikken ajourføres pt. ikke", last data 2025-10), and all
Prognosepriser grids were moved behind an AgroID login. The weekly grain
noteringer are therefore no longer publicly available on Farmtal.

Farmtal's own grain series cited "Kilde: DST", so we now read the same
underlying public source directly: Danmarks Statistik, Statistikbanken table
LPRIS10 "Salgspriser på udvalgte landbrugsprodukter" (monthly, kr. pr.
100 kg = DKK/hkg, ab gård). It is a clean JSON API — no browser needed.

Coverage vs. the old Farmtal page:
- hvede: DST "Hvede"  (was Brødhvede weekly notering)
- byg:   DST "Byg"    (was Foderbyg)
- raps:  DST "Raps"   (was Industriraps)
- majs:  NO source — the old page's Foderhvede proxy has no DST equivalent,
  so the indicator falls back to its last known value (stale=True) in the
  runner. Documented, not invented.

DEBUGGING: when fewer than the expected targets parse, the raw API payload
is dumped to data/_debug_farmtal_<date>.txt (uploaded as CI artifact).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .base import ApiScraper, today_iso, format_dk_number

log = logging.getLogger("scrapers")


# Targets: DST LPRIS10 product codes per output key. Keys/units are the
# frontend contract and must not change. "majs" has no product in LPRIS10
# (see module docstring) and is intentionally absent.
GRAIN_TARGETS = [
    {"code": "1000", "label": "Hvede", "key": "hvede", "unit": "DKK/hkg"},
    {"code": "1010", "label": "Byg", "key": "byg", "unit": "DKK/hkg"},
    {"code": "1025", "label": "Raps", "key": "raps", "unit": "DKK/hkg"},
]

_API_URL = (
    "https://api.statbank.dk/v1/data/LPRIS10/JSONSTAT"
    "?PRODUKT={codes}&ENHED=320&Tid=%2A"  # ENHED 320 = løbende priser
)


class FarmtalKorn(ApiScraper):
    name = "farmtal_korn"
    source_url = "https://www.statistikbanken.dk/LPRIS10"
    source_name = "Danmarks Statistik (LPRIS10)"

    def scrape(self) -> dict[str, dict[str, Any]]:
        codes = "%2C".join(t["code"] for t in GRAIN_TARGETS)
        raw = self.http_get(_API_URL.format(codes=codes),
                            headers={"Accept": "application/json"})
        if raw is None:
            return {}

        out: dict[str, dict[str, Any]] = {}
        try:
            ds = json.loads(raw)["dataset"]
            dim = ds["dimension"]
            product_index = dim["PRODUKT"]["category"]["index"]  # code -> pos
            periods = list(dim["Tid"]["category"]["index"].keys())  # "2026M05"
            values = ds["value"]  # product-major: len == n_products * n_periods
            n = len(periods)

            for target in GRAIN_TARGETS:
                pos = product_index.get(target["code"])
                if pos is None:
                    continue
                series = values[pos * n:(pos + 1) * n]
                # Latest month with a published (non-null, plausible) value.
                value = None
                period = None
                for per, v in zip(reversed(periods), reversed(series)):
                    if isinstance(v, (int, float)) and 50 <= v <= 800:
                        value, period = float(v), per
                        break
                if value is None:
                    continue
                # "2026M05" -> ISO date of that month (stable across reruns).
                date = f"{period[:4]}-{period[5:7]}-01" if "M" in period else today_iso()
                out[target["key"]] = {
                    "key": target["key"],
                    "icon": target["key"],
                    "name": target["label"],
                    "value": value,
                    "value_display": format_dk_number(value, target["unit"]),
                    "unit": target["unit"],
                    "date": date,
                    "source_url": self.source_url,
                    "source_name": self.source_name,
                    "stale": False,
                }
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("[%s] unexpected LPRIS10 payload: %s: %s",
                        self.name, type(exc).__name__, exc)

        # Debug dump when the payload did not yield what we expected.
        if len(out) < len(GRAIN_TARGETS):
            try:
                debug_dir = Path(__file__).resolve().parents[2] / "data"
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_path = debug_dir / f"_debug_farmtal_{today_iso()}.txt"
                debug_path.write_text(
                    f"=== farmtal_seges (DST LPRIS10) debug dump {today_iso()} ===\n"
                    f"matched: {sorted(out.keys())}\n"
                    f"missing: {[t['key'] for t in GRAIN_TARGETS if t['key'] not in out]}\n"
                    f"--- raw API response (first 8000 chars) ---\n"
                    + (raw or "")[:8000],
                    encoding="utf-8",
                )
                log.warning(
                    "[%s] only matched %d/%d targets — dumped payload to %s",
                    self.name, len(out), len(GRAIN_TARGETS), debug_path.name,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("[%s] failed to dump debug payload: %s", self.name, e)

        return out
