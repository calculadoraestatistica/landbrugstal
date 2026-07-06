#!/usr/bin/env python3
"""Country-agnostic scraper runner.

Reads tools/country.toml, instantiates every [[sources]] entry, merges the
returned indicators by key, and writes the basico + completo JSON files
declared under [output].

Run locally:
    python tools/scrape_country.py
    python tools/scrape_country.py --set basico
    python tools/scrape_country.py --no-playwright  # skip browser scrapers

Run in CI (GitHub Actions):
    pip install playwright
    playwright install --with-deps chromium
    python tools/scrape_country.py
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
CONFIG_PATH = TOOLS / "country.toml"


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def import_scraper(module: str, klass: str):
    sys.path.insert(0, str(TOOLS))
    mod = importlib.import_module(module)
    return getattr(mod, klass)


def build_fallback(key: str, cfg: dict, last_known: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a stale skeleton for the given indicator.

    If ``last_known`` carries a previous successful value for this key
    (from the existing on-disk JSON), keep that value visible so users see
    the most recent known number with a "Senest set: dd/mm" hint instead
    of a bare "Se kilde →" link. The indicator stays stale=True so the
    frontend can still flag it.
    """
    base = dict((cfg.get("fallback") or {}).get(key) or {})
    base["key"] = key
    base.setdefault("name", key)
    base.setdefault("unit", "")
    base.setdefault("source_url", "")
    base.setdefault("source_name", "")
    base["stale"] = True
    base["date"] = datetime.now(timezone.utc).date().isoformat()

    if last_known and last_known.get("value") is not None:
        base["value"] = last_known["value"]
        base["value_display"] = last_known.get("value_display") or base.get("value_display") or "—"
        base["last_seen_date"] = last_known.get("last_seen_date") or last_known.get("date") or ""
        base["last_seen_source"] = last_known.get("source_name") or base.get("source_name")
    else:
        base.setdefault("value", None)
        base.setdefault("value_display", "—")

    return base


def load_existing(path: Path) -> dict[str, dict[str, Any]]:
    """Return {key: indicator_dict} from an existing JSON file, or empty."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in (data.get("items") or []):
        key = item.get("key")
        if key:
            out[key] = item
    return out


HISTORY_MAX = 750  # entries kept per indicator (~3 years of weekdays)


def append_history(items: list[dict], path: Path) -> dict:
    """Append one daily snapshot per indicator to the history JSON.

    Structure: {"<key>": [{"d": "YYYY-MM-DD", "v": <float>}, ...], ...}
    - "d" is the quote's own date: for fresh values the scrape date, for stale
      fallbacks the last_seen_date — so re-running the scraper on the same day
      never duplicates entries (idempotent) and stale values are not re-logged
      forward as fake fresh points.
    - Caps each series at HISTORY_MAX entries (oldest dropped).
    """
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(history, dict):
            history = {}
    except (FileNotFoundError, ValueError):
        history = {}

    changed = False
    for it in items:
        key, value = it.get("key"), it.get("value")
        date = (it.get("last_seen_date") or it.get("date")) if it.get("stale") \
            else (it.get("date") or it.get("last_seen_date"))
        if not key or not date or not isinstance(value, (int, float)) or value <= 0:
            continue
        series = history.setdefault(key, [])
        existing = next((e for e in series if e.get("d") == date), None)
        if existing is None:
            series.append({"d": date, "v": value})
            series.sort(key=lambda e: e.get("d", ""))
            changed = True
        elif existing.get("v") != value:
            existing["v"] = value
            changed = True
        if len(series) > HISTORY_MAX:
            del series[:len(series) - HISTORY_MAX]

    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        os.replace(tmp, path)
        logging.info("wrote %s (%d indicators)", path.name, len(history))
    return history


def main() -> int:
    ap = argparse.ArgumentParser(description="Scrape per-country noteringer.")
    ap.add_argument("--set", choices=["basico", "completo", "all"], default="all")
    ap.add_argument("--no-playwright", action="store_true",
                    help="Skip browser-based scrapers (run only ApiScrapers).")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    cfg = load_config()

    if args.no_playwright:
        import scrapers.base as _b
        _b.PLAYWRIGHT_ENABLED = False

    # Run every source — failures stay isolated via safe_run().
    scraped: dict[str, dict[str, Any]] = {}
    for src in cfg.get("sources") or []:
        try:
            cls = import_scraper(src["module"], src["klass"])
        except Exception as exc:  # noqa: BLE001
            logging.error("import %s.%s failed: %s", src["module"], src["klass"], exc)
            continue
        out = cls().safe_run()
        for k, v in out.items():
            v["stale"] = False
            scraped[k] = v

    # Merge with fallback skeletons.
    indicators = cfg.get("indicators") or {}
    order = indicators.get("order") or []
    basico_keys = set(indicators.get("basico") or order)

    out_cfg = cfg.get("output") or {}
    basico_path = ROOT / out_cfg.get("basico_path", "data/noteringer.json")
    completo_path = ROOT / out_cfg.get("completo_path", "data/noteringer-completas.json")

    # Read the previous run's completo file so failed scrapes carry the
    # last known value forward as "Senest set: dd/mm".
    previous = load_existing(completo_path)

    def build_indicator(key: str) -> dict[str, Any]:
        if key in scraped:
            ind = scraped[key]
            # Track the date this fresh value was observed so the next run
            # can carry it forward if needed.
            ind["last_seen_date"] = ind.get("date", "")
            return ind
        return build_fallback(key, cfg, last_known=previous.get(key))

    completo_items = [build_indicator(k) for k in order]
    basico_items = [b for b in completo_items if b["key"] in basico_keys]

    payload_meta = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "country": (cfg.get("country") or {}).get("code", ""),
        "source": "; ".join(sorted({i["source_name"] for i in completo_items if i.get("source_name")})),
        "source_url": f"https://{(cfg.get('country') or {}).get('code', '').lower()}",
    }

    def write_json(path: Path, items: list[dict]):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**payload_meta, "items": items}
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        live = sum(1 for i in items if not i["stale"])
        stale = len(items) - live
        logging.info("wrote %s (%d items, %d live, %d stale)", path.name, len(items), live, stale)

    if args.set in ("basico", "all"):
        write_json(basico_path, basico_items)
    if args.set in ("completo", "all"):
        write_json(completo_path, completo_items)

    # Daily history snapshot (additive; failures never break the main output).
    try:
        history_path = ROOT / out_cfg.get("history_path", "data/noteringer-historik.json")
        append_history(completo_items, history_path)
    except Exception as exc:  # noqa: BLE001
        logging.warning("history append failed: %s", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
