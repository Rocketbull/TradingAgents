from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from activeportfolio.dataflows.market_data_store import load_history_window
from research.common.run_manager import ResearchRunManager


DEFAULT_SECTOR_ETFS = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Approximate an SP500-stock baseline backtest profile with sector ETF "
            "weights aggregated from a saved rebalance_log.jsonl."
        )
    )
    parser.add_argument(
        "--baseline-run-dir",
        default="eval_results/backtest/current_baseline_spy_offset_minus2_20260627",
        help="Directory containing rebalance_log.jsonl and optionally summary.json.",
    )
    parser.add_argument(
        "--classification-cache",
        default="data/market/metadata/yfinance_classification.csv",
        help="CSV with symbol,sector columns.",
    )
    parser.add_argument("--data-dir", default="data/market", help="Local market data root.")
    parser.add_argument("--output-dir", default="research/output", help="Research output root.")
    parser.add_argument("--run-tag", default=None, help="Optional output run tag.")
    parser.add_argument(
        "--target-field",
        default="target_weights",
        choices=["target_weights", "benchmark_weights", "raw_target_weights"],
        help="Weight field to collapse to sector ETF sleeves.",
    )
    parser.add_argument(
        "--missing-sector-mode",
        default="cash",
        choices=["cash", "redistribute"],
        help="Treat sectors without priced ETF data as cash, or redistribute mapped ETF weights to 100%.",
    )
    parser.add_argument(
        "--sector-etf",
        action="append",
        default=[],
        metavar="SECTOR=ETF",
        help="Override or add a sector ETF mapping. May be passed multiple times.",
    )
    parser.add_argument(
        "--symbol-sector",
        action="append",
        default=[],
        metavar="SYMBOL=SECTOR",
        help="Override or add a symbol sector mapping. May be passed multiple times.",
    )
    return parser.parse_args()


def _load_rebalance_log(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    rows = [r for r in rows if r.get("trade_date") and r.get("next_date")]
    if not rows:
        raise ValueError(f"No period rebalance rows found in {path}")
    return rows


def _load_sector_map(path: Path) -> dict[str, str]:
    df = pd.read_csv(path)
    if "symbol" not in df.columns or "sector" not in df.columns:
        raise ValueError(f"Expected symbol,sector columns in {path}")
    df = df.dropna(subset=["symbol", "sector"]).copy()
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["sector"] = df["sector"].astype(str).str.strip()
    return dict(zip(df["symbol"], df["sector"]))


def _parse_sector_overrides(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"Invalid --sector-etf override {raw!r}; expected SECTOR=ETF")
        sector, etf = raw.split("=", 1)
        sector = sector.strip()
        etf = etf.strip().upper()
        if not sector or not etf:
            raise ValueError(f"Invalid --sector-etf override {raw!r}; expected SECTOR=ETF")
        out[sector] = etf
    return out


def _parse_symbol_sector_overrides(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"Invalid --symbol-sector override {raw!r}; expected SYMBOL=SECTOR")
        symbol, sector = raw.split("=", 1)
        symbol = symbol.strip().upper()
        sector = sector.strip()
        if not symbol or not sector:
            raise ValueError(f"Invalid --symbol-sector override {raw!r}; expected SYMBOL=SECTOR")
        out[symbol] = sector
    return out


def _aggregate_sector_weights(
    rows: list[dict[str, Any]],
    sector_map: dict[str, str],
    target_field: str,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        weights = row.get(target_field, {})
        if not isinstance(weights, dict):
            continue
        sector_weights: dict[str, float] = {}
        unknown_weight = 0.0
        total_weight = 0.0
        nonzero_names = 0
        for symbol, raw_weight in weights.items():
            weight = float(raw_weight or 0.0)
            if not np.isfinite(weight) or abs(weight) <= 1e-10:
                continue
            total_weight += weight
            nonzero_names += 1
            sector = sector_map.get(str(symbol).upper())
            if sector:
                sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
            else:
                unknown_weight += weight
        for sector, weight in sector_weights.items():
            records.append(
                {
                    "trade_date": row["trade_date"],
                    "next_date": row["next_date"],
                    "sector": sector,
                    "weight": weight,
                    "stock_nonzero_count": nonzero_names,
                    "total_stock_weight": total_weight,
                    "unknown_sector_weight": unknown_weight,
                    "baseline_portfolio_return": float(row.get("portfolio_return", np.nan)),
                    "baseline_benchmark_return": float(row.get("benchmark_return", np.nan)),
                    "baseline_active_return": float(row.get("active_return", np.nan)),
                    "baseline_orders_count": int(row.get("orders_count", 0)),
                }
            )
        if unknown_weight:
            records.append(
                {
                    "trade_date": row["trade_date"],
                    "next_date": row["next_date"],
                    "sector": "Unknown",
                    "weight": unknown_weight,
                    "stock_nonzero_count": nonzero_names,
                    "total_stock_weight": total_weight,
                    "unknown_sector_weight": unknown_weight,
                    "baseline_portfolio_return": float(row.get("portfolio_return", np.nan)),
                    "baseline_benchmark_return": float(row.get("benchmark_return", np.nan)),
                    "baseline_active_return": float(row.get("active_return", np.nan)),
                    "baseline_orders_count": int(row.get("orders_count", 0)),
                }
            )
    if not records:
        raise ValueError(f"No nonzero weights found for target field {target_field!r}")
    return pd.DataFrame(records)


def _load_price_matrix(
    symbols: list[str],
    start_date: str,
    end_date: str,
    data_dir: str,
) -> tuple[pd.DataFrame, list[str]]:
    series: dict[str, pd.Series] = {}
    missing: list[str] = []
    for symbol in symbols:
        try:
            history = load_history_window(symbol, start_date, end_date, root_dir=data_dir)
        except (FileNotFoundError, ValueError):
            missing.append(symbol)
            continue
        price_col = "Adj Close" if "Adj Close" in history.columns else "Close"
        s = (
            history.assign(Date=lambda x: pd.to_datetime(x["Date"]))
            .set_index("Date")[price_col]
            .astype(float)
            .sort_index()
        )
        if s.notna().any():
            series[symbol] = s
        else:
            missing.append(symbol)
    if not series:
        raise ValueError("No ETF price series loaded.")
    prices = pd.concat(series.values(), axis=1, join="outer")
    prices.columns = list(series.keys())
    prices = prices.sort_index().ffill()
    return prices, missing


def _price_asof(prices: pd.DataFrame, symbol: str, date: str) -> float:
    loc = prices.index.searchsorted(pd.Timestamp(date), side="right") - 1
    if loc < 0:
        return float("nan")
    value = float(prices.iloc[loc][symbol])
    return value if np.isfinite(value) and value > 0.0 else float("nan")


def build_approximation(
    sector_weights: pd.DataFrame,
    sector_etfs: dict[str, str],
    prices: pd.DataFrame,
    missing_sector_mode: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    etf_weight_rows: list[dict[str, Any]] = []
    available_etfs = set(prices.columns)
    previous_etf_weights: dict[str, float] = {}

    for (trade_date, next_date), group in sector_weights.groupby(["trade_date", "next_date"], sort=True):
        sector_weight = group.groupby("sector")["weight"].sum().to_dict()
        etf_weights: dict[str, float] = {}
        missing_weight = 0.0
        unknown_weight = float(sector_weight.get("Unknown", 0.0))
        for sector, weight in sector_weight.items():
            if sector == "Unknown":
                continue
            etf = sector_etfs.get(sector)
            if etf and etf in available_etfs:
                etf_weights[etf] = etf_weights.get(etf, 0.0) + float(weight)
            else:
                missing_weight += float(weight)

        mapped_weight = sum(etf_weights.values())
        cash_weight = unknown_weight + missing_weight
        if missing_sector_mode == "redistribute" and mapped_weight > 0:
            etf_weights = {k: v / mapped_weight for k, v in etf_weights.items()}
            cash_weight = 0.0

        approx_return = 0.0
        for etf, weight in etf_weights.items():
            start_price = _price_asof(prices, etf, str(trade_date))
            end_price = _price_asof(prices, etf, str(next_date))
            etf_return = end_price / start_price - 1.0 if np.isfinite(start_price + end_price) else 0.0
            approx_return += float(weight) * etf_return
            etf_weight_rows.append(
                {
                    "trade_date": trade_date,
                    "next_date": next_date,
                    "etf": etf,
                    "weight": float(weight),
                    "period_return": etf_return,
                }
            )

        changed_etfs = {
            etf
            for etf in set(previous_etf_weights) | set(etf_weights)
            if abs(previous_etf_weights.get(etf, 0.0) - etf_weights.get(etf, 0.0)) > 1e-6
        }
        turnover = sum(
            abs(previous_etf_weights.get(etf, 0.0) - etf_weights.get(etf, 0.0))
            for etf in set(previous_etf_weights) | set(etf_weights)
        )
        first = group.iloc[0]
        rows.append(
            {
                "trade_date": trade_date,
                "next_date": next_date,
                "baseline_portfolio_return": float(first["baseline_portfolio_return"]),
                "baseline_benchmark_return": float(first["baseline_benchmark_return"]),
                "baseline_active_return": float(first["baseline_active_return"]),
                "sector_etf_return": approx_return,
                "sector_etf_active_return_vs_baseline": approx_return
                - float(first["baseline_portfolio_return"]),
                "mapped_weight": mapped_weight,
                "cash_or_unproxied_weight": cash_weight,
                "missing_priced_sector_weight": missing_weight,
                "unknown_sector_weight": unknown_weight,
                "etf_count": len(etf_weights),
                "etf_orders_count_proxy": len(changed_etfs),
                "etf_turnover_proxy": turnover,
                "baseline_orders_count": int(first["baseline_orders_count"]),
                "baseline_stock_nonzero_count": int(first["stock_nonzero_count"]),
            }
        )
        previous_etf_weights = etf_weights

    return pd.DataFrame(rows), pd.DataFrame(etf_weight_rows)


def _summary(periods: pd.DataFrame, sector_weights: pd.DataFrame, missing_etfs: list[str]) -> dict[str, Any]:
    active_diff = periods["sector_etf_active_return_vs_baseline"]
    baseline_growth = float((1.0 + periods["baseline_portfolio_return"]).prod() - 1.0)
    approx_growth = float((1.0 + periods["sector_etf_return"]).prod() - 1.0)
    tracking_error = float(active_diff.std(ddof=1) * np.sqrt(12.0)) if len(active_diff) > 1 else float("nan")
    return {
        "periods": int(periods.shape[0]),
        "baseline_total_return_over_rebalance_periods": baseline_growth,
        "sector_etf_total_return_over_rebalance_periods": approx_growth,
        "return_difference": approx_growth - baseline_growth,
        "annualized_monthly_tracking_error_vs_baseline": tracking_error,
        "mean_period_return_difference": float(active_diff.mean()),
        "mean_abs_period_return_difference": float(active_diff.abs().mean()),
        "mean_mapped_weight": float(periods["mapped_weight"].mean()),
        "mean_cash_or_unproxied_weight": float(periods["cash_or_unproxied_weight"].mean()),
        "max_cash_or_unproxied_weight": float(periods["cash_or_unproxied_weight"].max()),
        "mean_etf_count": float(periods["etf_count"].mean()),
        "mean_etf_orders_count_proxy": float(periods["etf_orders_count_proxy"].mean()),
        "mean_baseline_orders_count": float(periods["baseline_orders_count"].mean()),
        "mean_baseline_stock_nonzero_count": float(periods["baseline_stock_nonzero_count"].mean()),
        "missing_etf_price_symbols": missing_etfs,
        "latest_sector_weights": (
            sector_weights[sector_weights["trade_date"] == sector_weights["trade_date"].max()]
            .sort_values("weight", ascending=False)[["sector", "weight"]]
            .to_dict(orient="records")
        ),
    }


def main() -> None:
    args = parse_args()
    baseline_run_dir = Path(args.baseline_run_dir)
    rows = _load_rebalance_log(baseline_run_dir / "rebalance_log.jsonl")
    sector_map = _load_sector_map(Path(args.classification_cache))
    sector_map.update(_parse_symbol_sector_overrides(args.symbol_sector))
    sector_etfs = dict(DEFAULT_SECTOR_ETFS)
    sector_etfs.update(_parse_sector_overrides(args.sector_etf))

    sector_weights = _aggregate_sector_weights(rows, sector_map, args.target_field)
    etfs = sorted(set(sector_etfs.values()))
    start_date = str(sector_weights["trade_date"].min())
    end_date = str(sector_weights["next_date"].max())
    prices, missing_etfs = _load_price_matrix(etfs, start_date, end_date, args.data_dir)
    periods, etf_weights = build_approximation(
        sector_weights=sector_weights,
        sector_etfs=sector_etfs,
        prices=prices,
        missing_sector_mode=args.missing_sector_mode,
    )
    summary = _summary(periods, sector_weights, missing_etfs)

    params = {
        "baseline_run_dir": str(baseline_run_dir),
        "classification_cache": args.classification_cache,
        "data_dir": args.data_dir,
        "target_field": args.target_field,
        "missing_sector_mode": args.missing_sector_mode,
        "sector_etfs": sector_etfs,
        "symbol_sector_overrides": _parse_symbol_sector_overrides(args.symbol_sector),
        "start_date": start_date,
        "end_date": end_date,
    }
    manager = ResearchRunManager(
        out_dir=Path(args.output_dir),
        params=params,
        run_tag=args.run_tag,
        tag_prefix="sector_etf_baseline_approx",
    )
    run_dir = manager.run_dir()
    sector_weights.to_csv(run_dir / "sector_weights_by_rebalance.csv", index=False)
    periods.to_csv(run_dir / "approximation_periods.csv", index=False)
    etf_weights.to_csv(run_dir / "etf_weights_by_rebalance.csv", index=False)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manager.write_params(extra={"summary": summary})
    manager.write_manifest(
        artifacts={
            "summary": str(run_dir / "summary.json"),
            "sector_weights_by_rebalance": str(run_dir / "sector_weights_by_rebalance.csv"),
            "approximation_periods": str(run_dir / "approximation_periods.csv"),
            "etf_weights_by_rebalance": str(run_dir / "etf_weights_by_rebalance.csv"),
        },
        extra={"summary": summary},
    )
    print(json.dumps({"run_dir": str(run_dir), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
