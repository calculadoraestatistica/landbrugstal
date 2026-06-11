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


def build_fallback(key: str, cfg: dict) -> dict[str, Any]:
    base = dict((cfg.get("fallback") or {}).get(key) or {})
    base["key"] = key
    base.setdefault("name", key)
    base.setdefault("value", None)
    base.setdefault("value_display", "—")
    base.setdefault("unit", "")
    base.setdefault("source_url", "")
    base.setdefault("source_name", "")
    base["stale"] = True
    base["date"] = datetime.now(timezone.utc).date().isoformat()
    return base


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

    def build_indicator(key: str) -> dict[str, Any]:
        if key in scraped:
            return scraped[key]
        return build_fallback(key, cfg)

    completo_items = [build_indicator(k) for k in order]
    basico_items = [b for b in completo_items if b["key"] in basico_keys]

    out_cfg = cfg.get("output") or {}
    basico_path = ROOT / out_cfg.get("basico_path", "data/noteringer.json")
    completo_path = ROOT / out_cfg.get("completo_path", "data/noteringer-completas.json")

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
