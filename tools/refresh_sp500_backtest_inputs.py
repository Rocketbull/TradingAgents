from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.download_fundamentals import extract_row, parse_fundamentals_report
from tools.sp500_symbols import SP500_WIKI_URL, fetch_sp500_symbols
from tradingagents.dataflows.market_data_store import (
    download_history,
    parquet_path_for_symbol,
    save_history_parquet,
)
from tradingagents.dataflows.y_finance import get_fundamentals

DEFAULT_SYMBOLS_OUT = Path("data/universe/sp500/current/sp500_symbols.txt")
DEFAULT_SNAPSHOT_DIR = Path("data/universe/sp500/snapshots")
DEFAULT_MARKET_OUT_DIR = Path("data/market")
DEFAULT_FUNDAMENTALS_OUT_DIR = Path("data/fundamentals/sp500")
DEFAULT_BENCHMARK_SYMBOL = "SPY"
FUNDAMENTALS_COLUMNS = list(extract_row(symbol="", parsed={}).keys())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the active-portfolio backtest inputs for the S&P 500: "
            "snapshot current members, update market history, then update fundamentals."
        )
    )
    parser.add_argument(
        "--symbols-out",
        default=str(DEFAULT_SYMBOLS_OUT),
        help="Current S&P 500 symbol list output path.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(DEFAULT_SNAPSHOT_DIR),
        help="Directory for dated membership snapshots.",
    )
    parser.add_argument(
        "--snapshot-date",
        default=None,
        help="Snapshot date YYYY-MM-DD; defaults to current UTC date.",
    )
    parser.add_argument(
        "--benchmark-symbol",
        default=DEFAULT_BENCHMARK_SYMBOL,
        help="Benchmark symbol to also refresh for backtests.",
    )
    parser.add_argument(
        "--extra-symbol",
        action="append",
        default=[],
        help=(
            "Additional market-data symbols to refresh for backtests "
            "(repeatable, e.g. BTC-USD, GLD)."
        ),
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Market history start date YYYY-MM-DD.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Market history end date YYYY-MM-DD; defaults to today if omitted.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="History window in years when start/end are omitted.",
    )
    parser.add_argument(
        "--market-out-dir",
        default=str(DEFAULT_MARKET_OUT_DIR),
        help="Output root for market parquet files.",
    )
    parser.add_argument(
        "--overwrite-market",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overwrite existing market parquet files for the requested window.",
    )
    parser.add_argument(
        "--fundamentals-out-dir",
        default=str(DEFAULT_FUNDAMENTALS_OUT_DIR),
        help="Output directory for S&P 500 fundamentals snapshots.",
    )
    parser.add_argument(
        "--fundamentals-sleep-seconds",
        type=float,
        default=0.05,
        help="Delay between per-symbol fundamentals fetches.",
    )
    parser.add_argument(
        "--overwrite-fundamentals-latest",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Overwrite sp500_fundamentals_latest.* copies after each run.",
    )
    parser.add_argument(
        "--universe-limit",
        type=int,
        default=0,
        help="Optional limit on S&P 500 members for quick test runs. 0 means full universe.",
    )
    parser.add_argument(
        "--skip-market-data",
        action="store_true",
        help="Skip market history refresh.",
    )
    parser.add_argument(
        "--skip-fundamentals",
        action="store_true",
        help="Skip fundamentals refresh.",
    )
    return parser.parse_args()


def normalize_symbols(raw_symbols: Iterable[str]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        symbol = str(raw).strip().upper().replace(".", "-")
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def resolve_market_window(
    start_date: str | None,
    end_date: str | None,
    years: int,
) -> tuple[str, str]:
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    elif start_date or end_date:
        raise ValueError("Provide both --start-date and --end-date together, or omit both.")
    else:
        if years < 1:
            raise ValueError("--years must be >= 1")
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=365 * years)

    if start_dt > end_dt:
        raise ValueError("start-date must be <= end-date")
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def build_market_symbol_list(
    sp500_symbols: Sequence[str],
    benchmark_symbol: str,
    extra_symbols: Sequence[str],
) -> list[str]:
    merged = list(sp500_symbols) + [benchmark_symbol] + list(extra_symbols)
    return normalize_symbols(merged)


def write_sp500_symbol_outputs(
    symbols: Sequence[str],
    symbols_out: Path,
    snapshot_dir: Path,
    snapshot_date: str | None = None,
) -> dict[str, str]:
    if snapshot_date:
        snapshot_date = datetime.strptime(snapshot_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    else:
        snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    symbols_out.parent.mkdir(parents=True, exist_ok=True)
    symbols_out.write_text("\n".join(symbols) + "\n", encoding="utf-8")

    metadata_path = symbols_out.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(
            {
                "downloaded_at_utc": stamp,
                "source": SP500_WIKI_URL,
                "symbol_count": len(symbols),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"sp500_membership_{snapshot_date}.csv"
    pd.DataFrame(
        {
            "symbol": list(symbols),
            "source": SP500_WIKI_URL,
            "downloaded_at_utc": stamp,
        }
    ).to_csv(snapshot_path, index=False)

    print(f"[ok] S&P 500 symbols updated -> {symbols_out}")
    print(f"[ok] snapshot saved -> {snapshot_path}")
    return {
        "symbols_file": str(symbols_out),
        "symbols_metadata": str(metadata_path),
        "snapshot_csv": str(snapshot_path),
    }


def refresh_market_history(
    symbols: Sequence[str],
    start_date: str,
    end_date: str,
    out_dir: Path,
    overwrite: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    download_end = (
        datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    downloaded = 0
    skipped = 0
    failures: list[dict[str, str]] = []

    for idx, symbol in enumerate(symbols, start=1):
        target = parquet_path_for_symbol(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            root_dir=str(out_dir),
        )
        if target.exists() and not overwrite:
            skipped += 1
            print(f"[skip] market {idx}/{len(symbols)} {symbol}: {target}")
            continue

        try:
            df = download_history(symbol, start_date, download_end)
            output_path = save_history_parquet(
                df=df,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                root_dir=str(out_dir),
            )
            downloaded += 1
            print(f"[ok] market {idx}/{len(symbols)} {symbol}: rows={len(df)} -> {output_path}")
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
            print(f"[err] market {idx}/{len(symbols)} {symbol}: {exc}")

    return {
        "symbols_requested": len(symbols),
        "symbols_downloaded": downloaded,
        "symbols_skipped": skipped,
        "symbols_failed": len(failures),
        "failures": failures,
        "start_date": start_date,
        "end_date": end_date,
        "out_dir": str(out_dir),
    }


def refresh_fundamentals(
    symbols: Sequence[str],
    out_dir: Path,
    sleep_seconds: float,
    overwrite_latest: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"sp500_fundamentals_{stamp}.csv"
    jsonl_path = out_dir / f"sp500_fundamentals_{stamp}.jsonl"
    meta_path = out_dir / f"sp500_fundamentals_{stamp}.metadata.json"

    rows: list[dict[str, Any]] = []
    jsonl_records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for idx, symbol in enumerate(symbols, start=1):
        try:
            report = get_fundamentals(symbol)
            if report.startswith("No fundamentals data found"):
                failures.append({"symbol": symbol, "error": report})
                print(f"[warn] fundamentals {idx}/{len(symbols)} {symbol}: no data")
            elif report.startswith("Error retrieving fundamentals"):
                failures.append({"symbol": symbol, "error": report})
                print(f"[err] fundamentals {idx}/{len(symbols)} {symbol}: {report}")
            else:
                parsed = parse_fundamentals_report(report)
                rows.append(extract_row(symbol, parsed))
                jsonl_records.append(
                    {
                        "symbol": symbol,
                        "downloaded_at_utc": downloaded_at,
                        "fundamentals_report": report,
                        "parsed": parsed,
                    }
                )
                print(f"[ok] fundamentals {idx}/{len(symbols)} {symbol}")
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
            print(f"[err] fundamentals {idx}/{len(symbols)} {symbol}: {exc}")
        time.sleep(max(sleep_seconds, 0.0))

    if rows:
        df = pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=FUNDAMENTALS_COLUMNS)
    df.to_csv(csv_path, index=False)

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for rec in jsonl_records:
            handle.write(json.dumps(rec, ensure_ascii=True) + "\n")

    meta = {
        "downloaded_at_utc": downloaded_at,
        "symbols_requested": len(symbols),
        "symbols_succeeded": len(rows),
        "symbols_failed": len(failures),
        "source": "yfinance",
        "csv_path": str(csv_path),
        "jsonl_path": str(jsonl_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    latest_csv = out_dir / "sp500_fundamentals_latest.csv"
    latest_jsonl = out_dir / "sp500_fundamentals_latest.jsonl"
    latest_meta = out_dir / "sp500_fundamentals_latest.metadata.json"
    if overwrite_latest or not latest_csv.exists():
        shutil.copyfile(csv_path, latest_csv)
        shutil.copyfile(jsonl_path, latest_jsonl)
        shutil.copyfile(meta_path, latest_meta)

    return {
        "symbols_requested": len(symbols),
        "symbols_succeeded": len(rows),
        "symbols_failed": len(failures),
        "failures": failures,
        "csv_path": str(csv_path),
        "jsonl_path": str(jsonl_path),
        "metadata_path": str(meta_path),
    }


def run_refresh_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    sp500_symbols = fetch_sp500_symbols()
    if args.universe_limit > 0:
        sp500_symbols = sp500_symbols[: args.universe_limit]
    sp500_symbols = normalize_symbols(sp500_symbols)
    if not sp500_symbols:
        raise RuntimeError("Fetched empty S&P 500 symbol list.")

    symbol_outputs = write_sp500_symbol_outputs(
        symbols=sp500_symbols,
        symbols_out=Path(args.symbols_out),
        snapshot_dir=Path(args.snapshot_dir),
        snapshot_date=args.snapshot_date,
    )

    start_date, end_date = resolve_market_window(args.start_date, args.end_date, args.years)
    market_symbols = build_market_symbol_list(
        sp500_symbols=sp500_symbols,
        benchmark_symbol=args.benchmark_symbol,
        extra_symbols=args.extra_symbol,
    )

    summary: dict[str, Any] = {
        "run_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sp500_symbol_count": len(sp500_symbols),
        "sp500_symbols_file": symbol_outputs["symbols_file"],
        "snapshot_csv": symbol_outputs["snapshot_csv"],
        "market_symbol_count": len(market_symbols),
        "market_symbols": market_symbols,
        "steps": {
            "symbols": symbol_outputs,
        },
    }

    if args.skip_market_data:
        summary["steps"]["market"] = {"skipped": True}
    else:
        print(
            f"[step] refresh market history for {len(market_symbols)} symbols "
            f"({start_date}..{end_date})"
        )
        summary["steps"]["market"] = refresh_market_history(
            symbols=market_symbols,
            start_date=start_date,
            end_date=end_date,
            out_dir=Path(args.market_out_dir),
            overwrite=bool(args.overwrite_market),
        )

    if args.skip_fundamentals:
        summary["steps"]["fundamentals"] = {"skipped": True}
    else:
        print(f"[step] refresh fundamentals for {len(sp500_symbols)} S&P 500 symbols")
        summary["steps"]["fundamentals"] = refresh_fundamentals(
            symbols=sp500_symbols,
            out_dir=Path(args.fundamentals_out_dir),
            sleep_seconds=float(args.fundamentals_sleep_seconds),
            overwrite_latest=bool(args.overwrite_fundamentals_latest),
        )

    market_failed = int(summary["steps"].get("market", {}).get("symbols_failed", 0))
    fundamentals_failed = int(summary["steps"].get("fundamentals", {}).get("symbols_failed", 0))
    summary["has_errors"] = market_failed > 0 or fundamentals_failed > 0
    return summary


def main() -> None:
    args = parse_args()
    summary = run_refresh_pipeline(args)
    print(json.dumps(summary, indent=2))
    if summary.get("has_errors"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
