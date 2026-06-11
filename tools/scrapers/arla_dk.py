"""Arla DK — mælkepris (a-conto, øre/kg).

catalog.arla.com/ARLA/milk-price/arla-dk/ is server-side rendered but loads
a per-region table via JS. We let networkidle settle, then scan the body for
"<number> øre/kg" close to "Konventionel" / "Conventional".
"""
from __future__ import annotations
import re
from typing import Any
from .base import PlaywrightScraper, today_iso, format_dk_number, parse_dk_number


class ArlaMilk(PlaywrightScraper):
    name = "arla_milk"
    source_url = "https://catalog.arla.com/ARLA/milk-price/arla-dk/"
    source_name = "Arla DK"

    def extract(self, page) -> dict[str, dict[str, Any]]:
        try:
            page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        body = page.locator("body").inner_text()

        # Arla milk-price PDF view renders the DK section as:
        #   "Arlapris Juni 2026 - DK 4.2% fedt og 3.4% protein, DKK øre/kg mælk.
        #    Acontopris ... Arlapris Konventionel 302.2 11.2 7.5 320.9 Øko ..."
        # The first number after "Konventionel" inside the "DK ... øre/kg"
        # section is the acontopris in øre/kg.
        m = re.search(
            r"(?:DKK\s*øre/kg|øre\s*/\s*kg\s*mælk)[\s\S]{0,400}?Konventionel\s+(\d{2,4}[.,]?\d{0,3})",
            body, re.IGNORECASE,
        )
        if not m:
            # Fallback: any "Konventionel <num>" near "DK".
            m = re.search(
                r"-\s*DK[\s\S]{0,400}?Konventionel\s+(\d{2,4}[.,]?\d{0,3})",
                body, re.IGNORECASE,
            )
        if not m:
            return {}
        v = parse_dk_number(m.group(1))
        if v is None or v < 100 or v > 1200:  # sanity for ore/kg milk
            return {}
        return {
            "maelkepris": {
                "key": "maelkepris",
                "icon": "maelk",
                "name": "Mælkepris (Arla DK, konventionel)",
                "value": v,
                "value_display": format_dk_number(v, "øre/kg"),
                "unit": "øre/kg",
                "date": today_iso(),
                "source_url": self.source_url,
                "source_name": self.source_name,
                "stale": False,
            }
        }
