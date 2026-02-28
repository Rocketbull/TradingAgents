from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.portfolio import (
    AlphaModel,
    AttributionEngine,
    PortfolioOptimizer,
    Rebalancer,
    RiskModel,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run active portfolio pipeline demo using local parquet market data."
    )
    parser.add_argument(
        "--trade-date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Trade date for snapshot (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--symbol-file",
        default="data/market/sp500_symbols.txt",
        help="Path to symbol list file (one symbol per line).",
    )
    parser.add_argument(
        "--data-root",
        default="data/market",
        help="Root path containing symbol parquet folders.",
    )
    parser.add_argument(
        "--universe-size",
        type=int,
        default=50,
        help="Number of symbols to include from symbol file.",
    )
    parser.add_argument(
        "--benchmark-symbol",
        default="SPY",
        help="Benchmark symbol to force include in universe.",
    )
    parser.add_argument(
        "--out",
        default="eval_results/portfolio/demo_run.json",
        help="Output JSON report path.",
    )
    return parser.parse_args()


def load_symbols(path: Path, universe_size: int, benchmark_symbol: str) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Symbol file not found: {path}")
    symbols = [line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    symbols = symbols[:universe_size]
    bench = benchmark_symbol.upper()
    if bench not in symbols:
        symbols = [bench] + symbols
    return list(dict.fromkeys(symbols))


def parse_dates_from_name(path: Path) -> Optional[tuple[datetime, datetime]]:
    # Expected filename: history_YYYY-MM-DD_YYYY-MM-DD.parquet
    stem = path.stem
    if not stem.startswith("history_"):
        return None
    parts = stem.split("_")
    if len(parts) != 3:
        return None
    try:
        start = datetime.strptime(parts[1], "%Y-%m-%d")
        end = datetime.strptime(parts[2], "%Y-%m-%d")
        return start, end
    except ValueError:
        return None


def choose_parquet(symbol_dir: Path, trade_dt: datetime) -> Optional[Path]:
    candidates: list[tuple[datetime, datetime, Path]] = []
    for path in symbol_dir.glob("history_*.parquet"):
        parsed = parse_dates_from_name(path)
        if parsed is None:
            continue
        start, end = parsed
        if start <= trade_dt <= end:
            candidates.append((start, end, path))
    if not candidates:
        return None
    # Prefer latest end-date, then latest start-date.
    candidates.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return candidates[0][2]


def build_close_matrix(
    symbols: Iterable[str], data_root: Path, trade_dt: datetime
) -> pd.DataFrame:
    series: Dict[str, pd.Series] = {}
    for symbol in symbols:
        symbol_dir = data_root / symbol
        if not symbol_dir.exists():
            continue
        parquet_path = choose_parquet(symbol_dir, trade_dt)
        if parquet_path is None:
            continue
        df = pd.read_parquet(parquet_path)
        if "Date" not in df.columns:
            continue
        price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        if price_col not in df.columns:
            continue
        s = (
            df[["Date", price_col]]
            .rename(columns={price_col: symbol})
            .assign(Date=lambda x: pd.to_datetime(x["Date"]))
            .set_index("Date")[symbol]
            .sort_index()
        )
        s = s[s.index <= pd.Timestamp(trade_dt)]
        if s.empty:
            continue
        series[symbol] = s

    if len(series) < 2:
        raise ValueError("Need at least 2 symbols with local data coverage for demo run.")

    closes = pd.concat(series.values(), axis=1, join="outer")
    closes.columns = list(series.keys())
    closes = closes.sort_index().ffill().dropna(axis=1, how="any")
    if closes.shape[1] < 2:
        raise ValueError("Insufficient aligned close price history after preprocessing.")
    return closes


def equal_weights(symbols: Iterable[str]) -> Dict[str, float]:
    syms = list(symbols)
    w = 1.0 / len(syms)
    return {s: w for s in syms}


def main() -> None:
    args = parse_args()
    trade_dt = datetime.strptime(args.trade_date, "%Y-%m-%d")

    symbols = load_symbols(
        path=Path(args.symbol_file),
        universe_size=args.universe_size,
        benchmark_symbol=args.benchmark_symbol,
    )
    closes = build_close_matrix(
        symbols=symbols,
        data_root=Path(args.data_root),
        trade_dt=trade_dt,
    )

    cfg = DEFAULT_CONFIG.copy()
    cfg["benchmark_symbol"] = args.benchmark_symbol.upper()

    alpha_model = AlphaModel()
    risk_model = RiskModel(lookback_days=int(cfg.get("alpha_lookback_days", 252)))
    optimizer = PortfolioOptimizer(
        risk_aversion=float(cfg.get("risk_aversion", 3.0)),
        max_weight=float(cfg.get("max_weight", 0.05)),
        turnover_limit=float(cfg.get("turnover_limit", 0.20)),
    )
    rebalancer = Rebalancer(transaction_cost_bps=float(cfg.get("transaction_cost_bps", 5.0)))
    attribution = AttributionEngine()

    alpha_scores = alpha_model.score(closes)
    covariance = risk_model.covariance(closes)
    benchmark_symbol = cfg["benchmark_symbol"]
    benchmark_weights = {s: 0.0 for s in alpha_scores.index}
    if benchmark_symbol in benchmark_weights:
        benchmark_weights[benchmark_symbol] = 1.0
    else:
        benchmark_weights = equal_weights(alpha_scores.index)

    current_weights = equal_weights(alpha_scores.index)
    target_weights = optimizer.optimize(
        alpha_scores=alpha_scores,
        covariance=covariance,
        current_weights=current_weights,
        benchmark_weights=benchmark_weights,
    )
    orders = rebalancer.generate_orders(
        current_weights=current_weights,
        target_weights=target_weights,
        portfolio_value=float(cfg.get("portfolio_value", 1_000_000.0)),
    )
    realized_proxy = closes.pct_change().iloc[-1].reindex(alpha_scores.index).fillna(0.0)
    metrics = attribution.diagnostics(
        alpha_scores=alpha_scores,
        realized_returns=realized_proxy,
        target_weights=target_weights,
    )

    report = {
        "run_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trade_date": args.trade_date,
        "symbol_count": int(len(alpha_scores)),
        "symbols": list(alpha_scores.index),
        "benchmark_symbol": benchmark_symbol,
        "top_alpha_scores": dict(alpha_scores.sort_values(ascending=False).head(10).round(6)),
        "target_weights": {k: round(float(v), 8) for k, v in target_weights.items()},
        "rebalance_orders_count": len(orders),
        "rebalance_orders_sample": orders[:20],
        "portfolio_metrics": {k: float(v) for k, v in metrics.items()},
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[ok] demo run completed for {args.trade_date}")
    print(f"[ok] symbols used: {len(alpha_scores)}")
    print(f"[ok] rebalance orders: {len(orders)}")
    print(f"[ok] output: {out_path}")


if __name__ == "__main__":
    main()
