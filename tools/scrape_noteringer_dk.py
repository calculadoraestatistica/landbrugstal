#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_noteringer_dk.py
=======================

Scraper de noteringer (spot-priser) for den danske landbrugssektor.

Producerer:
  - data/noteringer-dk.json            (basico: hvede, raps, mælkepris, grisenotering)
  - data/noteringer-dk-completas.json  (komplet: alle ovenstående + byg, majs, kreaturnotering, EUR/DKK, USD/DKK)

Kilder:
  - SEGES Farmtal Online   -> hvede, byg, raps, majs
      https://farmtalonline.dlbr.dk/
  - Arla DK milk catalog   -> mælkepris (konventionel + økologisk)
      https://catalog.arla.com/ARLA/milk-price/arla-dk/
  - Danish Crown ejer      -> grisenotering, kreaturnotering
      https://ejer.danishcrown.com/
  - Danske Svineproducenter (fallback for grisenotering)
      https://danskesvineproducenter.dk/noteringer/
  - Nationalbanken         -> EUR/DKK, USD/DKK
      https://www.nationalbanken.dk/

Output-format (matcher det eksisterende noteringer-dk.json som js/noteringer-dk.js læser):
  {
    "updated_at": "<ISO-8601>",
    "source": "<navn>",
    "source_url": "<url>",
    "items": [
      {
        "key": "hvede",
        "icon": "hvede",
        "name": "Brødhvede",
        "value": 152.50,
        "value_display": "152,50 DKK/hkg",
        "unit": "DKK/hkg",
        "date": "2026-06-10",
        "source_url": "...",
        "source_name": "SEGES Farmtal Online",
        "stale": false
      },
      ...
    ]
  }

Brug:
  python tools/scrape_noteringer_dk.py --set basico
  python tools/scrape_noteringer_dk.py --set completo
  python tools/scrape_noteringer_dk.py --set all          # skriv begge filer

Krav: kun standardbiblioteket (urllib, html.parser, json, re).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import html.parser as _hp
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

USER_AGENT = "landbrugstal-noteringer/1.0 (+https://landbrugstal.dk)"
HTTP_TIMEOUT = 20  # sekunder

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")

OUT_BASICO = os.path.join(DATA_DIR, "noteringer-dk.json")
OUT_COMPLETO = os.path.join(DATA_DIR, "noteringer-dk-completas.json")

# Indikatorer i "basico" pakken (4 essentielle)
KEYS_BASICO = {"hvede", "raps", "maelkepris", "grisenotering"}

# Rækkefølge i output
ORDER = [
    "hvede",
    "byg",
    "raps",
    "majs",
    "maelkepris",
    "grisenotering",
    "kreaturnotering",
    "eur_dkk",
    "usd_dkk",
]

# Sidste-kendte fallback-værdier (placeholders), brugt når alle scrape-forsøg fejler.
# Disse markeres med stale=true så frontenden kan vise advarsel.
FALLBACK: Dict[str, Dict[str, Any]] = {
    "hvede": {
        "icon": "hvede",
        "name": "Brødhvede",
        "value": None,
        "value_display": "—",
        "unit": "DKK/hkg",
        "source_url": "https://farmtalonline.dlbr.dk/",
        "source_name": "SEGES Farmtal Online",
    },
    "byg": {
        "icon": "byg",
        "name": "Foderbyg",
        "value": None,
        "value_display": "—",
        "unit": "DKK/hkg",
        "source_url": "https://farmtalonline.dlbr.dk/",
        "source_name": "SEGES Farmtal Online",
    },
    "raps": {
        "icon": "raps",
        "name": "Raps",
        "value": None,
        "value_display": "—",
        "unit": "DKK/hkg",
        "source_url": "https://farmtalonline.dlbr.dk/",
        "source_name": "SEGES Farmtal Online",
    },
    "majs": {
        "icon": "majs",
        "name": "Foderkorn (Majs, Euronext)",
        "value": None,
        "value_display": "—",
        "unit": "EUR/t",
        "source_url": "https://live.euronext.com/en/product/commodities-futures/EMA-DPAR",
        "source_name": "Euronext Paris",
    },
    "maelkepris": {
        "icon": "maelk",
        "name": "Mælkepris (Arla DK, konventionel)",
        "value": None,
        "value_display": "—",
        "unit": "øre/kg",
        "source_url": "https://catalog.arla.com/ARLA/milk-price/arla-dk/",
        "source_name": "Arla Foods",
    },
    "grisenotering": {
        "icon": "gris",
        "name": "Svinenotering (slagtevægt)",
        "value": None,
        "value_display": "—",
        "unit": "DKK/kg",
        "source_url": "https://ejer.danishcrown.com/",
        "source_name": "Danish Crown",
    },
    "kreaturnotering": {
        "icon": "kreatur",
        "name": "Kreaturnotering (Ungtyr)",
        "value": None,
        "value_display": "—",
        "unit": "DKK/kg",
        "source_url": "https://ejer.danishcrown.com/",
        "source_name": "Danish Crown",
    },
    "eur_dkk": {
        "icon": "eur_dkk",
        "name": "EUR/DKK",
        "value": None,
        "value_display": "—",
        "unit": "DKK",
        "source_url": "https://www.nationalbanken.dk/",
        "source_name": "Nationalbanken",
    },
    "usd_dkk": {
        "icon": "usd_dkk",
        "name": "USD/DKK",
        "value": None,
        "value_display": "—",
        "unit": "DKK",
        "source_url": "https://www.nationalbanken.dk/",
        "source_name": "Nationalbanken",
    },
}


# ---------------------------------------------------------------------------
# HTTP-hjælpere
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = HTTP_TIMEOUT) -> Optional[str]:
    """GET en URL og returnér body som tekst (utf-8 best-effort). None ved fejl."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "da-DK,da;q=0.9,en;q=0.6",
        },
    )
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            # forsøg utf-8, fallback latin-1
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as exc:
        sys.stderr.write("[warn] http_get failed for {0}: {1}\n".format(url, exc))
        return None
    except Exception as exc:  # noqa: BLE001 — never crash on a single source
        sys.stderr.write("[warn] http_get unexpected error for {0}: {1}\n".format(url, exc))
        return None


# ---------------------------------------------------------------------------
# HTML-stripper (stdlib html.parser)
# ---------------------------------------------------------------------------

class _TextExtractor(_hp.HTMLParser):
    """Trækker ren tekst ud, holder styr på simple tabel-rækker."""

    SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag in ("br", "tr", "p", "div", "li", "td", "th"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in ("tr", "p", "div", "li"):
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.parts.append(data)


def html_to_text(html_doc: str) -> str:
    """Konverter HTML til en flad tekst-repræsentation til regex-parsing."""
    p = _TextExtractor()
    try:
        p.feed(html_doc)
    except Exception:  # noqa: BLE001
        return ""
    return re.sub(r"[ \t]+", " ", "".join(p.parts))


# ---------------------------------------------------------------------------
# Værdi-hjælpere
# ---------------------------------------------------------------------------

_DECIMAL_RX = re.compile(r"(\d+(?:\.\d+)?(?:,\d+)?|\d{1,4}(?:\.\d{3})+(?:,\d+)?)")


def parse_dk_number(text: str) -> Optional[float]:
    """Parse a number that may be DK-formatted (1.234,56 / 1234,56 / 152,5)
    or US-formatted (747.43). Heuristic:
      - if both ',' and '.': dot=thousands, comma=decimal → strip dot, swap comma to dot
      - if ',' only: comma=decimal → swap to dot
      - if '.' only AND the part after dot has 1-2 digits: it's a decimal (US format)
      - if '.' only AND the part after dot has exactly 3 digits AND total digits > 3:
            it's a thousands separator → strip
      - else float() directly
    """
    if not text:
        return None
    m = _DECIMAL_RX.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    has_comma = "," in raw
    has_dot = "." in raw
    if has_comma and has_dot:
        raw = raw.replace(".", "").replace(",", ".")
    elif has_comma:
        raw = raw.replace(",", ".")
    elif has_dot:
        # Only a dot. Decide thousands vs decimal by length of fractional part.
        before, _, after = raw.partition(".")
        if len(after) == 3 and len(before) >= 1 and "." not in before:
            # Could be 1.234 = thousands OR 1.234 = decimal. If the integer is ≥4
            # digits or contains multiple dots, treat as thousands. Otherwise
            # leave as decimal — too ambiguous to override.
            pass  # keep dot as decimal
        # else keep as decimal
    try:
        return float(raw)
    except ValueError:
        return None


def format_dk(value: Optional[float], unit: str) -> str:
    if value is None:
        return "—"
    # dansk lokal-formatering: komma som decimal, punkt som tusindseparator
    if value >= 1000:
        formatted = "{0:,.2f}".format(value).replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        formatted = "{0:.2f}".format(value).replace(".", ",")
    return "{0} {1}".format(formatted, unit)


def today_iso() -> str:
    return _dt.date.today().isoformat()


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Indikator-scrapere
#   Hver returnerer en dict klar til at blive flettet med FALLBACK-skabelonen,
#   eller None hvis intet brugbart blev hentet.
# ---------------------------------------------------------------------------

def scrape_farmtal_korn() -> Dict[str, Dict[str, Any]]:
    """Hent hvede / byg / raps / majs fra SEGES Farmtal Online.

    Farmtal er en JSP-app — sidens layout er ikke garanteret. Vi forsøger at
    finde produkt-navne + dansk decimaltal i samme linje af den HTML-stripped
    tekst, og rapporterer per indikator.
    """
    out: Dict[str, Dict[str, Any]] = {}
    url = "https://farmtalonline.dlbr.dk/Navigation/NavigationsMenu.aspx"
    body = http_get(url)
    if not body:
        return out

    text = html_to_text(body)

    patterns = [
        ("hvede", "Brødhvede", re.compile(r"Br[øo]dhvede[^\n]{0,80}?(\d+[.,]?\d*)", re.IGNORECASE)),
        ("byg",   "Foderbyg",  re.compile(r"Foderbyg[^\n]{0,80}?(\d+[.,]?\d*)",       re.IGNORECASE)),
        ("raps",  "Raps",      re.compile(r"Raps[^\n]{0,80}?(\d+[.,]?\d*)",            re.IGNORECASE)),
    ]

    for key, label, rx in patterns:
        m = rx.search(text)
        if not m:
            continue
        val = parse_dk_number(m.group(1))
        if val is None:
            continue
        out[key] = {
            "name": label,
            "value": val,
            "value_display": format_dk(val, "DKK/hkg"),
            "unit": "DKK/hkg",
            "date": today_iso(),
            "source_url": url,
            "source_name": "SEGES Farmtal Online",
        }
    return out


def scrape_arla_milk() -> Optional[Dict[str, Any]]:
    """Hent Arla DK konventionel a-conto-mælkepris (øre/kg).

    Siden er statisk HTML — vi leder efter et tal efterfulgt af "øre/kg" eller
    "ore/kg" tæt på ordet "konventionel".
    """
    url = "https://catalog.arla.com/ARLA/milk-price/arla-dk/"
    body = http_get(url)
    if not body:
        return None
    text = html_to_text(body)
    # forsøg: "Konventionel ... 320,5 øre/kg"
    rx = re.compile(r"konventionel[^\n]{0,200}?(\d+[.,]?\d*)\s*(?:øre|ore)\s*/\s*kg", re.IGNORECASE)
    m = rx.search(text)
    if not m:
        # generic fallback: any "<num> øre/kg"
        m = re.search(r"(\d+[.,]?\d*)\s*(?:øre|ore)\s*/\s*kg", text, re.IGNORECASE)
    if not m:
        return None
    val = parse_dk_number(m.group(1))
    if val is None:
        return None
    return {
        "name": "Mælkepris (Arla DK, konventionel)",
        "value": val,
        "value_display": format_dk(val, "øre/kg"),
        "unit": "øre/kg",
        "date": today_iso(),
        "source_url": url,
        "source_name": "Arla Foods",
    }


def scrape_danish_crown() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Hent svinenotering + kreaturnotering fra Danish Crown ejerportal.

    Notering-siderne lever på faste paths under /da-dk/andelsejere/.
    Grise: tabel med vægtklasser → vi læser basis-rækken (73,0-97,9 kg) som
    er den toneangivende slagtevægt.
    Kreatur: tager første kr/kg-tal vi finder efter "Notering".
    Returnerer (gris, kreatur). Begge kan være None.
    """
    gris: Optional[Dict[str, Any]] = None
    kreatur: Optional[Dict[str, Any]] = None

    # GRIS
    url_g = "https://ejer.danishcrown.com/da-dk/andelsejere/gris/notering/aktuel-grisenotering/"
    body = http_get(url_g)
    if body:
        text = html_to_text(body)
        # Find tabel-række "73,0-97,9 | ... | <kr/kg uge X> | <kr/kg uge X-1>"
        # Tabellen er rendered med linieskift mellem celler — brug [\s\S].
        m = re.search(r"73,0[–—-]97,9[\s\S]{0,80}?\|[\s\S]{0,40}?(\d+[.,]\d+)", text)
        if m:
            v = parse_dk_number(m.group(1))
            if v is not None:
                gris = {
                    "name": "Grisenotering (Danish Crown, basis 73-98 kg)",
                    "value": v,
                    "value_display": format_dk(v, "DKK/kg"),
                    "unit": "DKK/kg",
                    "date": today_iso(),
                    "source_url": url_g,
                    "source_name": "Danish Crown",
                }

    # KREATUR
    url_k = "https://ejer.danishcrown.com/da-dk/andelsejere/kreatur/notering/aktuel-kreaturnotering/"
    body = http_get(url_k)
    if body:
        text = html_to_text(body)
        # Den løbende notering vises som "Ungtyr ... kr/kg" eller bare tal i en tabel.
        # Forsøg: "Ungtyr R 5-6 | ... | <kr/kg>" eller første kr-tal under "Kreaturnotering"
        idx = text.find("Kreaturnotering")
        if idx > 0:
            block = text[idx:idx + 3000]
            # Find numbers in form X,XX (typisk 20-40 kr/kg for ungtyr)
            for m in re.finditer(r"(\d{2}[.,]\d{2})\s*\|", block):
                v = parse_dk_number(m.group(1))
                if v is not None and 10 <= v <= 60:
                    kreatur = {
                        "name": "Kreaturnotering (Ungtyr, Danish Crown)",
                        "value": v,
                        "value_display": format_dk(v, "DKK/kg"),
                        "unit": "DKK/kg",
                        "date": today_iso(),
                        "source_url": url_k,
                        "source_name": "Danish Crown",
                    }
                    break

    # Fallback til Danske Svineproducenter for gris (slagtesvin Uge X)
    if gris is None:
        url2 = "https://danskesvineproducenter.dk/noteringer/"
        body2 = http_get(url2)
        if body2:
            text2 = html_to_text(body2)
            # Find Slagtesvin section → Danish Crown row → current week (first kr value)
            idx = text2.find("Slagtesvin")
            if idx > 0:
                block = text2[idx:idx + 2500]
                m = re.search(r"Danish Crown\s*\|\s*kr\.?\s*\|\s*(\d+[.,]\d+)\s*\|", block)
                if m:
                    v = parse_dk_number(m.group(1))
                    if v is not None:
                        gris = {
                            "name": "Slagtesvinepris (Danske Svineproducenter)",
                            "value": v,
                            "value_display": format_dk(v, "DKK/kg"),
                            "unit": "DKK/kg",
                            "date": today_iso(),
                            "source_url": url2,
                            "source_name": "Danske Svineproducenter",
                        }

    return gris, kreatur


def scrape_nationalbanken_fx() -> Dict[str, Optional[float]]:
    """Hent EUR/DKK + USD/DKK fra Nationalbanken.

    Bruger den offentlige statbank-CSV-endpoint, som er stabil og uden auth.
    Faldger tilbage til exchangerate.host hvis Nationalbanken ikke svarer.
    """
    out: Dict[str, Optional[float]] = {"EUR": None, "USD": None}

    # Nationalbanken — daily rates as XML
    url = "https://www.nationalbanken.dk/api/currencyratesxml?lang=en"
    body = http_get(url)
    if body:
        # XML format: <currency code="EUR" desc="Euro" rate="747.43"/>
        # desc sits between code and rate, so match with [^>]*.
        for m in re.finditer(r'code="([A-Z]{3})"[^>]*?\brate="([\d.,]+)"', body):
            code = m.group(1)
            if code in ("EUR", "USD"):
                # Rate er US-format med . som decimal; parse direkte.
                try:
                    raw = float(m.group(2))
                except ValueError:
                    raw = None
                if raw is not None:
                    # Nationalbanken angiver rate som DKK pr 100 enheder
                    out[code] = raw / 100.0

    # Fallback til exchangerate.host
    if out["EUR"] is None or out["USD"] is None:
        body2 = http_get("https://api.exchangerate.host/latest?base=DKK&symbols=EUR,USD")
        if body2:
            try:
                payload = json.loads(body2)
                rates = payload.get("rates") or {}
                if out["EUR"] is None and rates.get("EUR"):
                    out["EUR"] = 1.0 / float(rates["EUR"])
                if out["USD"] is None and rates.get("USD"):
                    out["USD"] = 1.0 / float(rates["USD"])
            except (ValueError, TypeError, json.JSONDecodeError):
                pass

    return out


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

def build_indicator(key: str, scraped: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Flet scraped data over en FALLBACK-skabelon. Markér stale hvis intet hentet."""
    base = dict(FALLBACK.get(key, {}))
    base["key"] = key
    if not scraped or scraped.get("value") is None:
        base["stale"] = True
        base.setdefault("date", today_iso())
        return base
    merged = dict(base)
    merged.update(scraped)
    merged["key"] = key
    merged["stale"] = False
    # garantér icon
    if "icon" not in merged:
        merged["icon"] = base.get("icon", key)
    return merged


def collect_all() -> Dict[str, Dict[str, Any]]:
    """Kør alle scrapere, hver i try/except, og returnér key -> indicator-dict."""
    scraped: Dict[str, Dict[str, Any]] = {}

    # SEGES Farmtal (hvede / byg / raps)
    try:
        farmtal = scrape_farmtal_korn()
        for k, v in farmtal.items():
            scraped[k] = v
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[warn] farmtal scrape failed: {0}\n".format(exc))

    # Arla mælkepris
    try:
        m = scrape_arla_milk()
        if m is not None:
            scraped["maelkepris"] = m
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[warn] arla scrape failed: {0}\n".format(exc))

    # Danish Crown gris + kreatur
    try:
        gris, kreatur = scrape_danish_crown()
        if gris is not None:
            scraped["grisenotering"] = gris
        if kreatur is not None:
            scraped["kreaturnotering"] = kreatur
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[warn] danish crown scrape failed: {0}\n".format(exc))

    # FX fra Nationalbanken
    try:
        fx = scrape_nationalbanken_fx()
        if fx.get("EUR") is not None:
            scraped["eur_dkk"] = {
                "name": "EUR/DKK",
                "value": fx["EUR"],
                "value_display": "{0:.4f} DKK".format(fx["EUR"]).replace(".", ","),
                "unit": "DKK",
                "date": today_iso(),
                "source_url": "https://www.nationalbanken.dk/",
                "source_name": "Nationalbanken",
            }
        if fx.get("USD") is not None:
            scraped["usd_dkk"] = {
                "name": "USD/DKK",
                "value": fx["USD"],
                "value_display": "{0:.4f} DKK".format(fx["USD"]).replace(".", ","),
                "unit": "DKK",
                "date": today_iso(),
                "source_url": "https://www.nationalbanken.dk/",
                "source_name": "Nationalbanken",
            }
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[warn] FX scrape failed: {0}\n".format(exc))

    # Saml indikatorer (inkl. fallback for dem vi ikke nåede)
    out: Dict[str, Dict[str, Any]] = {}
    for key in ORDER:
        out[key] = build_indicator(key, scraped.get(key))
    return out


def write_json(path: str, items_keys: List[str], all_indicators: Dict[str, Dict[str, Any]]) -> None:
    items: List[Dict[str, Any]] = []
    for key in ORDER:
        if key not in items_keys:
            continue
        ind = all_indicators.get(key)
        if ind is None:
            continue
        items.append(ind)

    payload = {
        "updated_at": now_iso(),
        "source": "SEGES Farmtal, Arla, Danish Crown, Nationalbanken",
        "source_url": "https://landbrugstal.dk/cotacoes.html",
        "items": items,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    sys.stdout.write("[ok] wrote {0} ({1} items)\n".format(path, len(items)))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape DK landbrugsnoteringer -> JSON")
    ap.add_argument(
        "--set",
        dest="which_set",
        choices=("basico", "completo", "all"),
        default="all",
        help="basico (4 essentielle), completo (alle), eller all (skriv begge filer).",
    )
    args = ap.parse_args(argv)

    all_indicators = collect_all()

    basico_keys = [k for k in ORDER if k in KEYS_BASICO]
    completo_keys = list(ORDER)

    wrote_anything = False
    if args.which_set in ("basico", "all"):
        write_json(OUT_BASICO, basico_keys, all_indicators)
        wrote_anything = True
    if args.which_set in ("completo", "all"):
        write_json(OUT_COMPLETO, completo_keys, all_indicators)
        wrote_anything = True

    # Diagnose: hvor mange indikatorer var fresh vs stale?
    stale = sum(1 for k in completo_keys if all_indicators[k].get("stale"))
    fresh = len(completo_keys) - stale
    sys.stdout.write("[info] fresh={0}, stale={1}\n".format(fresh, stale))

    return 0 if wrote_anything else 1


if __name__ == "__main__":
    raise SystemExit(main())
