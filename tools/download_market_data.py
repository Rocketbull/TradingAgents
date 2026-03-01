from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tradingagents.dataflows.market_data_store import (
    download_history,
    parquet_path_for_symbol,
    save_history_parquet,
)
from tools.sp500_symbols import fetch_sp500_symbols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Yahoo Finance history and store as parquet."
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Ticker symbols, e.g. SPY TSLA AAPL",
    )
    parser.add_argument("--start-date", help="Start date YYYY-MM-DD")
    parser.add_argument(
        "--end-date",
        help="End date YYYY-MM-DD (inclusive from user perspective)",
    )
    parser.add_argument(
        "--sp500",
        action="store_true",
        help="Download all current S&P 500 constituents from Wikipedia.",
    )
    parser.add_argument(
        "--crypto",
        action="store_true",
        help="Download default crypto universe (BTC-USD, ETH-USD).",
    )
    parser.add_argument(
        "--commodities",
        action="store_true",
        help="Download default commodity universe (gold, silver, copper futures).",
    )
    parser.add_argument(
        "--symbols-file",
        default=None,
        help="Optional text file with one ticker per line.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="When start/end are omitted, download this many years ending today (default: 5).",
    )
    parser.add_argument("--out-dir", default="data/market", help="Output root directory")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing parquet files if present",
    )
    return parser.parse_args()


def normalize_symbols(raw_symbols: List[str]) -> List[str]:
    seen = set()
    symbols = []
    for raw in raw_symbols:
        for token in raw.split(","):
            s = token.strip().upper()
            if s and s not in seen:
                symbols.append(s)
                seen.add(s)
    return symbols


def load_symbols_file(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Symbols file not found: {path}")
    rows = [line.strip().upper() for line in p.read_text(encoding="utf-8").splitlines()]
    return normalize_symbols(rows)


def main() -> None:
    args = parse_args()
    if args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d").strftime("%Y-%m-%d")
        end_inclusive = datetime.strptime(args.end_date, "%Y-%m-%d")
        end_date = end_inclusive.strftime("%Y-%m-%d")
    elif args.start_date or args.end_date:
        raise SystemExit("Provide both --start-date and --end-date together, or omit both.")
    else:
        if args.years < 1:
            raise SystemExit("--years must be >= 1")
        end_inclusive = datetime.today()
        start_date = (end_inclusive - timedelta(days=365 * args.years)).strftime(
            "%Y-%m-%d"
        )
        end_date = end_inclusive.strftime("%Y-%m-%d")

    download_end = (end_inclusive + timedelta(days=1)).strftime("%Y-%m-%d")
    merged = list(args.symbols or [])
    if args.sp500:
        merged.extend(fetch_sp500_symbols())
    if args.crypto:
        merged.extend(["BTC-USD", "ETH-USD"])
    if args.commodities:
        merged.extend(["GC=F", "SI=F", "HG=F"])
    if args.symbols_file:
        merged.extend(load_symbols_file(args.symbols_file))
    symbols = normalize_symbols(merged)

    if not symbols:
        raise SystemExit(
            "No valid symbols provided. Use --symbols/--symbols-file and/or --sp500/--crypto/--commodities."
        )

    print(
        f"Downloading {len(symbols)} symbols from {start_date} to {end_date} "
        f"(Yahoo end={download_end}, exclusive)."
    )

    for symbol in symbols:
        target = parquet_path_for_symbol(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            root_dir=args.out_dir,
        )
        if target.exists() and not args.overwrite:
            print(f"[skip] {symbol}: {target}")
            continue

        df = download_history(symbol, start_date, download_end)
        output_path = save_history_parquet(
            df=df,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            root_dir=args.out_dir,
        )
        print(f"[ok] {symbol}: rows={len(df)} -> {output_path}")


if __name__ == "__main__":
    main()
