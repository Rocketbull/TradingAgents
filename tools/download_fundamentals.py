from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from tools.sp500_symbols import fetch_sp500_symbols
except ModuleNotFoundError:
    from sp500_symbols import fetch_sp500_symbols
from activeportfolio.dataflows.y_finance import get_fundamentals

DEFAULT_SYMBOLS_FILE = Path("data/universe/sp500/current/sp500_symbols.txt")
LEGACY_SYMBOLS_FILE = Path("data/market/sp500_symbols.txt")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download yfinance fundamentals for a symbol list (default: S&P 500)."
    )
    parser.add_argument(
        "--symbols-file",
        default=str(DEFAULT_SYMBOLS_FILE),
        help="Text file with one symbol per line.",
    )
    parser.add_argument(
        "--sp500-fetch",
        action="store_true",
        help="Refresh S&P 500 symbols from Wikipedia before downloading fundamentals.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/fundamentals/sp500",
        help="Directory for output files.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.05,
        help="Delay between symbol fetches to reduce request burst.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of symbols for quick test. 0 means all symbols.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite latest output symlink/copy files.",
    )
    return parser.parse_args()


def load_symbols(path: Path, refresh_sp500: bool) -> list[str]:
    if path == DEFAULT_SYMBOLS_FILE and not path.exists() and LEGACY_SYMBOLS_FILE.exists():
        path = LEGACY_SYMBOLS_FILE

    if refresh_sp500:
        symbols = fetch_sp500_symbols()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(symbols) + "\n", encoding="utf-8")
        return symbols

    if not path.exists():
        raise FileNotFoundError(
            f"Symbols file not found: {path}. Use --sp500-fetch to generate it."
        )
    rows = [line.strip().upper().replace(".", "-") for line in path.read_text().splitlines()]
    symbols: list[str] = []
    seen = set()
    for symbol in rows:
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


FIELD_MAP = {
    "Name": "name",
    "Sector": "sector",
    "Industry": "industry",
    "Market Cap": "market_cap",
    "PE Ratio (TTM)": "trailing_pe",
    "Forward PE": "forward_pe",
    "PEG Ratio": "peg_ratio",
    "Price to Book": "price_to_book",
    "EPS (TTM)": "trailing_eps",
    "Forward EPS": "forward_eps",
    "Dividend Yield": "dividend_yield",
    "Beta": "beta",
    "Revenue (TTM)": "total_revenue",
    "Gross Profit": "gross_profit",
    "EBITDA": "ebitda",
    "Net Income": "net_income",
    "Profit Margin": "profit_margins",
    "Operating Margin": "operating_margins",
    "Return on Equity": "return_on_equity",
    "Return on Assets": "return_on_assets",
    "Debt to Equity": "debt_to_equity",
    "Current Ratio": "current_ratio",
    "Book Value": "book_value",
    "Free Cash Flow": "free_cashflow",
}


def _parse_value(value: str):
    value = value.strip()
    if value == "":
        return None
    low = value.lower()
    if low in {"none", "nan", "n/a"}:
        return None
    try:
        if any(ch in value for ch in [".", "e", "E"]):
            return float(value)
        return int(value)
    except ValueError:
        return value


def parse_fundamentals_report(report: str) -> dict:
    parsed: dict = {}
    for line in report.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ": " not in line:
            continue
        label, raw_value = line.split(": ", 1)
        key = FIELD_MAP.get(label)
        if key:
            parsed[key] = _parse_value(raw_value)
    return parsed


def extract_row(symbol: str, parsed: dict) -> dict:
    return {
        "symbol": symbol,
        "name": parsed.get("name"),
        "sector": parsed.get("sector"),
        "industry": parsed.get("industry"),
        "market_cap": parsed.get("market_cap"),
        "trailing_pe": parsed.get("trailing_pe"),
        "forward_pe": parsed.get("forward_pe"),
        "peg_ratio": parsed.get("peg_ratio"),
        "price_to_book": parsed.get("price_to_book"),
        "trailing_eps": parsed.get("trailing_eps"),
        "forward_eps": parsed.get("forward_eps"),
        "dividend_yield": parsed.get("dividend_yield"),
        "beta": parsed.get("beta"),
        "profit_margins": parsed.get("profit_margins"),
        "operating_margins": parsed.get("operating_margins"),
        "return_on_equity": parsed.get("return_on_equity"),
        "return_on_assets": parsed.get("return_on_assets"),
        "debt_to_equity": parsed.get("debt_to_equity"),
        "current_ratio": parsed.get("current_ratio"),
        "book_value": parsed.get("book_value"),
        "free_cashflow": parsed.get("free_cashflow"),
        "total_revenue": parsed.get("total_revenue"),
        "gross_profit": parsed.get("gross_profit"),
        "ebitda": parsed.get("ebitda"),
        "net_income": parsed.get("net_income"),
    }


def main() -> None:
    args = parse_args()
    symbols_path = Path(args.symbols_file)
    symbols = load_symbols(symbols_path, refresh_sp500=args.sp500_fetch)

    if args.limit > 0:
        symbols = symbols[: args.limit]
    if not symbols:
        raise SystemExit("No symbols available.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"sp500_fundamentals_{stamp}.csv"
    jsonl_path = out_dir / f"sp500_fundamentals_{stamp}.jsonl"
    meta_path = out_dir / f"sp500_fundamentals_{stamp}.metadata.json"

    rows: list[dict] = []
    jsonl_records: list[dict] = []
    errors = 0

    print(f"[start] fundamentals download for {len(symbols)} symbols")
    for idx, symbol in enumerate(symbols, start=1):
        try:
            report = get_fundamentals(symbol)
            if report.startswith("No fundamentals data found"):
                errors += 1
                print(f"[warn] {idx}/{len(symbols)} {symbol}: no data")
                continue
            if report.startswith("Error retrieving fundamentals"):
                errors += 1
                print(f"[err] {idx}/{len(symbols)} {symbol}: {report}")
                continue
            parsed = parse_fundamentals_report(report)
            row = extract_row(symbol, parsed)
            rows.append(row)
            jsonl_records.append(
                {
                    "symbol": symbol,
                    "downloaded_at_utc": downloaded_at,
                    "fundamentals_report": report,
                    "parsed": parsed,
                }
            )
            print(f"[ok] {idx}/{len(symbols)} {symbol}")
        except Exception as exc:
            errors += 1
            print(f"[err] {idx}/{len(symbols)} {symbol}: {exc}")
        time.sleep(max(args.sleep_seconds, 0.0))

    df = pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)
    df.to_csv(csv_path, index=False)
    with jsonl_path.open("w", encoding="utf-8") as f:
        for rec in jsonl_records:
            f.write(json.dumps(rec, ensure_ascii=True) + "\n")

    meta = {
        "downloaded_at_utc": downloaded_at,
        "symbols_requested": len(symbols),
        "symbols_succeeded": len(rows),
        "symbols_failed": errors,
        "source": "yfinance",
        "symbols_file": str(symbols_path),
        "csv_path": str(csv_path),
        "jsonl_path": str(jsonl_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    latest_csv = out_dir / "sp500_fundamentals_latest.csv"
    latest_jsonl = out_dir / "sp500_fundamentals_latest.jsonl"
    latest_meta = out_dir / "sp500_fundamentals_latest.metadata.json"
    if args.overwrite or not latest_csv.exists():
        shutil.copyfile(csv_path, latest_csv)
        shutil.copyfile(jsonl_path, latest_jsonl)
        shutil.copyfile(meta_path, latest_meta)

    print(f"[done] success={len(rows)} failed={errors}")
    print(f"[out] {csv_path}")
    print(f"[out] {jsonl_path}")
    print(f"[out] {meta_path}")


if __name__ == "__main__":
    main()
