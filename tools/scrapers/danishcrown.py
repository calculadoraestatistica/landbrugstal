"""Danish Crown — grisenotering + kreaturnotering.

Layout as of 2026-06/07 (both pages relaunched on a Nuxt shell):

- The whole ejer.danishcrown.com site sits behind a "Cookie Information"
  consent wall ("Du giver dit samtykke ... hvis du trykker OK"). The OK
  button may live in the main frame or an embedded consent frame, so we
  scan every frame before extracting.
- Grisenotering: the page renders one table per category (slagtegrise,
  søer, orner, undervægtige). The slagtegrise table lists price per
  slaughter-weight band with the newest week in the first value column;
  the *basis* band is the one with the highest price (77,0-101,9 kg as of
  July 2025 — bands change over time, so we pick the max instead of
  hard-coding the band).
- Kreaturnotering: no longer an HTML table. The page is an accordion of
  years, each holding weekly "Uge NN YYYY" links to PDFs
  (/media/<hash>/uge-NN-YYYY.pdf, hash changes every week). We expand the
  newest year, download the newest week's PDF and read the
  "Ungtyre 12-24 mdr." 280 kg row, class R (3rd price column of the
  E/U/R/O/P+/P scale). Prices are "Afregningspriser inkl. Ejersatser".
  PDF text needs `pypdf` (preferred) or PyMuPDF — CI installs pypdf.

DEBUGGING: on a failed extraction the rendered body text (or PDF text) is
dumped to data/_debug_danishcrown_<name>_<date>.txt so layout changes are
diagnosable from workflow artifacts.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
from pathlib import Path
from typing import Any

from .base import PlaywrightScraper, today_iso, format_dk_number, parse_dk_number

log = logging.getLogger("scrapers")


def _dismiss_cookie_wall(page) -> None:
    """Close the Cookie Information consent wall (button may be in any frame)."""
    selectors = (
        "button:has-text('OK')",
        "button:has-text('Kun nødvendige cookies')",
        "button:has-text('Accepter alle')",
        "button:has-text('Acceptér alle')",
    )
    for sel in selectors:
        for frame in page.frames:
            try:
                btn = frame.locator(sel).first
                if btn.is_visible(timeout=800):
                    btn.click(timeout=2500)
                    page.wait_for_timeout(1200)
                    return
            except Exception:  # noqa: BLE001
                continue


def _dump_debug(name: str, text: str, note: str = "") -> None:
    """Save extraction context to data/ so CI artifacts capture layout changes."""
    try:
        debug_dir = Path(__file__).resolve().parents[2] / "data"
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / f"_debug_danishcrown_{name}_{today_iso()}.txt"
        path.write_text(
            f"=== danishcrown_{name} debug dump {today_iso()} ===\n{note}\n"
            f"--- text (first 8000 chars) ---\n" + text[:8000],
            encoding="utf-8",
        )
        log.warning("[danishcrown_%s] extraction failed — dumped to %s", name, path.name)
    except Exception as exc:  # noqa: BLE001
        log.warning("[danishcrown_%s] failed to write debug dump: %s", name, exc)


class DanishCrownGris(PlaywrightScraper):
    name = "danishcrown_gris"
    source_url = "https://ejer.danishcrown.com/da-dk/andelsejere/gris/notering/aktuel-grisenotering/"
    source_name = "Danish Crown"

    def extract(self, page) -> dict[str, dict[str, Any]]:
        _dismiss_cookie_wall(page)
        page.wait_for_selector("text=Grisenotering", timeout=20_000)
        page.wait_for_timeout(500)
        body = page.locator("body").inner_text()

        # Slice out the slagtegrise table: from the "Grisenotering" heading to
        # the "Kødprocent" section that follows it (excludes søer/orner rows).
        start = body.find("Grisenotering")
        if start == -1:
            _dump_debug("gris", body, "no 'Grisenotering' heading found")
            return {}
        end = body.find("Kødprocent", start)
        section = body[start:end] if end != -1 else body[start:start + 4000]

        # Rows look like "77-101,9 <tabs/newlines> 6,90 ... 6,90" — weight band
        # followed by the newest week's kr/kg price. Bands may be "50,0-58,9",
        # "77-101,9" or open-ended "110,0-".
        rows: list[tuple[str, float]] = []
        for m in re.finditer(
            r"(\d{2,3}(?:,\d)?\s*[-–—]\s*(?:\d{2,3}(?:,\d)?)?)[^\d]{0,40}?(\d{1,2},\d{2})",
            section,
        ):
            band = re.sub(r"\s+", "", m.group(1))
            val = parse_dk_number(m.group(2))
            if val is not None and 0.5 <= val <= 25.0:
                rows.append((band, val))

        if len(rows) < 5:  # not the weight table we expected
            _dump_debug("gris", body, f"only {len(rows)} band rows matched")
            return {}

        # The basis band carries the headline notering = highest price.
        band, val = max(rows, key=lambda r: r[1])
        return {
            "grisenotering": {
                "key": "grisenotering",
                "icon": "gris",
                "name": f"Grisenotering (basis {band} kg)",
                "value": val,
                "value_display": format_dk_number(val, "DKK/kg"),
                "unit": "DKK/kg",
                "date": today_iso(),
                "source_url": self.source_url,
                "source_name": self.source_name,
                "stale": False,
            }
        }


def _pdf_to_text(pdf_bytes: bytes) -> str | None:
    """Extract text from the weekly notering PDF (pypdf, PyMuPDF fallback)."""
    try:
        import io
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("[danishcrown_kreatur] pypdf failed: %s", exc)
    try:
        import fitz  # PyMuPDF
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            return "\n".join(pg.get_text() for pg in doc)
    except ImportError:
        log.error("[danishcrown_kreatur] no PDF library — pip install pypdf")
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("[danishcrown_kreatur] PyMuPDF failed: %s", exc)
        return None


class DanishCrownKreatur(PlaywrightScraper):
    name = "danishcrown_kreatur"
    source_url = "https://ejer.danishcrown.com/da-dk/andelsejere/kreatur/notering/aktuel-kreaturnotering/"
    source_name = "Danish Crown"

    def extract(self, page) -> dict[str, dict[str, Any]]:
        _dismiss_cookie_wall(page)
        try:
            page.wait_for_selector("button.c-accordion-header", timeout=20_000)
        except Exception:
            _dump_debug("kreatur", page.locator("body").inner_text(),
                        "no year accordion found")
            return {}

        # Expand the newest year (accordion headers are "2026", "2025", ...).
        years: list[int] = []
        headers = page.locator("button.c-accordion-header")
        for i in range(headers.count()):
            try:
                txt = headers.nth(i).inner_text(timeout=2_000).strip()
            except Exception:  # noqa: BLE001
                continue
            if re.fullmatch(r"20\d\d", txt):
                years.append(int(txt))
        if not years:
            _dump_debug("kreatur", page.locator("body").inner_text(),
                        "no year headers in accordion")
            return {}
        newest_year = max(years)
        page.locator("button.c-accordion-header", has_text=str(newest_year)).first.click()
        page.wait_for_timeout(1_500)

        # Collect weekly PDF links: /media/<hash>/uge-NN-YYYY.pdf
        weeks: list[tuple[int, int, str]] = []  # (year, week, href)
        links = page.locator(f"a[href*='uge-']")
        for i in range(links.count()):
            href = links.nth(i).get_attribute("href") or ""
            m = re.search(r"uge-(\d{1,2})-(\d{4})\.pdf", href)
            if m:
                weeks.append((int(m.group(2)), int(m.group(1)), href))
        if not weeks:
            _dump_debug("kreatur", page.locator("body").inner_text(),
                        f"no uge-*.pdf links after expanding {newest_year}")
            return {}
        year, week, href = max(weeks)
        pdf_url = href if href.startswith("http") else f"https://ejer.danishcrown.com{href}"

        resp = page.request.get(pdf_url)
        if not resp.ok:
            log.warning("[%s] PDF fetch %s -> HTTP %d", self.name, pdf_url, resp.status)
            return {}
        text = _pdf_to_text(resp.body())
        if not text:
            return {}

        # "Ungtyre 12-24 mdr." section, 280 kg row, columns E U R O P+ P.
        # pypdf may glue the numbers together ("42,6442,2441,84...") so we
        # just findall the dd,dd tokens after "280 Kg".
        m = re.search(r"Ungtyre\s*12\s*-\s*24[\s\S]{0,500}?280\s*Kg\.?([^\n]*\n?[^\n]*)", text)
        if not m:
            _dump_debug("kreatur", text, f"no 'Ungtyre 12-24 ... 280 Kg' row in {pdf_url}")
            return {}
        nums = re.findall(r"\d{2},\d{2}", m.group(1))
        if len(nums) < 3:
            _dump_debug("kreatur", text, f"too few prices in 280 kg row: {nums}")
            return {}
        val = parse_dk_number(nums[2])  # class R = 3rd column
        if val is None or not (10.0 <= val <= 80.0):
            _dump_debug("kreatur", text, f"R price out of range: {nums[2]!r}")
            return {}

        # Date the quote by its own ISO week (idempotent across reruns).
        # DC publishes the coming week in advance — clamp to today so the
        # frontend never shows a future date.
        try:
            monday = _dt.date.fromisocalendar(year, week, 1)
            quote_date = min(monday, _dt.date.today()).isoformat()
        except ValueError:
            quote_date = today_iso()
        return {
            "kreaturnotering": {
                "key": "kreaturnotering",
                "icon": "kreatur",
                "name": "Kreaturnotering (Ungtyr R, 280 kg)",
                "value": val,
                "value_display": format_dk_number(val, "DKK/kg"),
                "unit": "DKK/kg",
                "date": quote_date,
                "source_url": self.source_url,
                "source_name": self.source_name,
                "stale": False,
            }
        }
