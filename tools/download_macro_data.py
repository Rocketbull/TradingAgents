from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from activeportfolio.dataflows.fred_macro import FREDMacroStore
from activeportfolio.default_config import DEFAULT_CONFIG


def load_config_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config JSON must be an object: {path}")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and cache FRED macro history as parquet."
    )
    parser.add_argument(
        "--config-json",
        default=None,
        help="Optional JSON file with regime config overrides.",
    )
    parser.add_argument(
        "--series",
        nargs="+",
        default=None,
        help="Explicit FRED series IDs to cache, e.g. UNRATE CPIAUCSL INDPRO.",
    )
    parser.add_argument(
        "--regime-defaults",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include macro_v1 default regime series from config.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Lookback window in days. Defaults to regime_macro_lookback_days from config.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output root directory. Defaults to regime_macro_data_root from config.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue downloading remaining series if one request fails.",
    )
    return parser.parse_args()


def normalize_series_ids(raw_series: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in raw_series:
        for token in str(raw).split(","):
            series_id = token.strip().upper()
            if series_id and series_id not in seen:
                seen.add(series_id)
                out.append(series_id)
    return out


def regime_default_series_ids(config: dict[str, Any]) -> list[str]:
    keys = [
        "regime_macro_unemployment_series_id",
        "regime_macro_inflation_series_id",
        "regime_macro_growth_series_id",
        "regime_macro_curve_series_id",
        "regime_macro_policy_series_id",
        "regime_macro_stress_series_id",
    ]
    return normalize_series_ids([str(config.get(key, "")).strip() for key in keys])


def build_download_plan(args: argparse.Namespace) -> tuple[list[str], str, int, str]:
    config = DEFAULT_CONFIG.copy()
    config.update(load_config_json(args.config_json))

    merged: list[str] = []
    if args.regime_defaults:
        merged.extend(regime_default_series_ids(config))
    if args.series:
        merged.extend(args.series)
    series_ids = normalize_series_ids(merged)
    if not series_ids:
        raise ValueError("No FRED series selected. Use --series and/or --regime-defaults.")

    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    else:
        end_date = datetime.today().strftime("%Y-%m-%d")

    lookback_days = int(
        args.lookback_days
        if args.lookback_days is not None
        else config.get("regime_macro_lookback_days", 800)
    )
    if lookback_days < 1:
        raise ValueError("lookback_days must be >= 1")

    out_dir = str(args.out_dir or config.get("regime_macro_data_root", "data/macro/fred"))
    return series_ids, end_date, lookback_days, out_dir


def main() -> None:
    args = parse_args()
    series_ids, end_date, lookback_days, out_dir = build_download_plan(args)
    store = FREDMacroStore(root_dir=out_dir, auto_download=True)
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime(
        "%Y-%m-%d"
    )

    print(
        f"Downloading {len(series_ids)} FRED series from {start_date} to {end_date} "
        f"into {out_dir}."
    )

    failures: list[tuple[str, str]] = []
    for series_id in series_ids:
        try:
            paths = store.warm_series([series_id], end_date=end_date, lookback_days=lookback_days)
            print(f"[ok] {series_id}: {paths[0]}")
        except Exception as exc:
            failures.append((series_id, str(exc)))
            print(f"[error] {series_id}: {exc}")
            if not args.continue_on_error:
                raise

    if failures:
        print(f"[warn] completed with {len(failures)} failures.")
        for series_id, reason in failures:
            print(f"[warn] {series_id}: {reason}")
    else:
        print("[ok] all downloads completed successfully.")


if __name__ == "__main__":
    main()
