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

from activeportfolio.backtest.data_loader import LocalParquetDataLoader
from research.common import ResearchRunManager


def parse_args() -> argparse.Namespace:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config-json", default=None, help="Optional JSON config file.")
    pre_args, _ = pre.parse_known_args()

    cfg: dict[str, Any] = {}
    if pre_args.config_json:
        cfg_path = Path(pre_args.config_json)
        if not cfg_path.exists():
            raise FileNotFoundError(f"Config not found: {cfg_path}")
        loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Config JSON must be an object.")
        cfg = loaded

    p = argparse.ArgumentParser(
        description="Research strategy: long S&P 500 names while 5-day MA is above 20-day MA."
    )
    p.add_argument("--config-json", default=pre_args.config_json, help="Optional JSON config file.")
    p.add_argument("--start-date", default=cfg.get("start_date", "2021-04-18"), help="YYYY-MM-DD")
    p.add_argument("--end-date", default=cfg.get("end_date", "2026-04-17"), help="YYYY-MM-DD")
    p.add_argument(
        "--universe-source",
        default=cfg.get("universe_source", "sp500_snapshot"),
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
    )
    p.add_argument("--symbol-file", default=cfg.get("symbol_file", "data/universe/sp500/current/sp500_symbols.txt"))
    p.add_argument("--snapshot-dir", default=cfg.get("snapshot_dir", "data/universe/sp500/snapshots"))
    p.add_argument("--data-root", default=cfg.get("data_root", "data/market"))
    p.add_argument("--benchmark-symbol", default=cfg.get("benchmark_symbol", "SPY"))
    p.add_argument("--fallback-symbol", default=cfg.get("fallback_symbol", "SPY"))
    p.add_argument("--universe-size", type=int, default=int(cfg.get("universe_size", 500)))
    p.add_argument("--fast-window", type=int, default=int(cfg.get("fast_window", 5)))
    p.add_argument("--slow-window", type=int, default=int(cfg.get("slow_window", 20)))
    p.add_argument("--transaction-cost-bps", type=float, default=float(cfg.get("transaction_cost_bps", 5.0)))
    p.add_argument("--out-dir", default=cfg.get("out_dir", "research/output"))
    p.add_argument("--run-tag", default=cfg.get("run_tag", None))
    return p.parse_args()


def _annualized_return(total_return: float, periods: int) -> float:
    if periods <= 0:
        return float("nan")
    growth = 1.0 + float(total_return)
    if growth <= 0.0:
        return float("nan")
    return float(growth ** (252.0 / float(periods)) - 1.0)


def _max_drawdown(nav: pd.Series) -> float:
    if nav.empty:
        return float("nan")
    return float((nav / nav.cummax() - 1.0).min())


def _sharpe(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    std = float(returns.std(ddof=0))
    if not np.isfinite(std) or std == 0.0:
        return float("nan")
    return float(returns.mean() / std * np.sqrt(252.0))


def _normalize_weights(signal: pd.DataFrame) -> pd.DataFrame:
    active_counts = signal.sum(axis=1)
    return signal.div(active_counts.replace(0, np.nan), axis=0).fillna(0.0)


def build_ma_crossover_portfolio(
    close: pd.DataFrame,
    fast_window: int = 5,
    slow_window: int = 20,
    transaction_cost_bps: float = 5.0,
    evaluation_start: str | pd.Timestamp | None = None,
    evaluation_end: str | pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if fast_window < 2:
        raise ValueError("fast_window must be >= 2")
    if slow_window <= fast_window:
        raise ValueError("slow_window must be greater than fast_window")
    if close.shape[1] < 1:
        raise ValueError("close must contain at least one symbol")

    clean_close = close.sort_index().apply(pd.to_numeric, errors="coerce").ffill()
    eval_start_ts = pd.Timestamp(evaluation_start) if evaluation_start is not None else None
    eval_end_ts = pd.Timestamp(evaluation_end) if evaluation_end is not None else None
    fast_ma = clean_close.rolling(fast_window, min_periods=fast_window).mean()
    slow_ma = clean_close.rolling(slow_window, min_periods=slow_window).mean()
    above = fast_ma > slow_ma
    prev_above = above.shift(1, fill_value=False)
    cross_up = above & ~prev_above
    cross_down = ~above & prev_above

    # The crossover is known after the close, so tradeable exposure starts on the next close-to-close return.
    weights = _normalize_weights(above.shift(1, fill_value=False).astype(float))
    daily_returns = clean_close.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    gross_returns = weights.mul(daily_returns, axis=0).sum(axis=1)

    turnover = weights.diff().abs().sum(axis=1).fillna(weights.sum(axis=1))
    costs = turnover * (float(transaction_cost_bps) / 10000.0)
    net_returns = gross_returns - costs
    nav = (1.0 + net_returns).cumprod()

    valid_mask = slow_ma.notna().any(axis=1)
    if eval_start_ts is not None:
        valid_mask &= clean_close.index >= eval_start_ts
    if eval_end_ts is not None:
        valid_mask &= clean_close.index <= eval_end_ts
    daily = pd.DataFrame(
        {
            "date": clean_close.index,
            "active_names": above.sum(axis=1).astype(int).values,
            "buy_signals": cross_up.sum(axis=1).astype(int).values,
            "sell_signals": cross_down.sum(axis=1).astype(int).values,
            "gross_return": gross_returns.values,
            "turnover": turnover.values,
            "cost": costs.values,
            "net_return": net_returns.values,
            "nav": nav.values,
            "drawdown": (nav / nav.cummax() - 1.0).values,
        }
    )
    daily = daily[valid_mask.values].reset_index(drop=True)
    if daily.empty:
        raise ValueError("No valid rows after moving-average warmup.")

    eval_above = above.loc[valid_mask]
    eval_cross_up = cross_up.loc[valid_mask]
    eval_cross_down = cross_down.loc[valid_mask]
    eval_prices = clean_close.loc[valid_mask]
    signal_by_symbol = pd.DataFrame(
        {
            "symbol": clean_close.columns,
            "days_with_price": eval_prices.notna().sum(axis=0).astype(int).values,
            "buy_signal_count": eval_cross_up.sum(axis=0).astype(int).values,
            "sell_signal_count": eval_cross_down.sum(axis=0).astype(int).values,
            "days_active": eval_above.sum(axis=0).astype(int).values,
            "days_active_ratio": eval_above.mean(axis=0).astype(float).values,
        }
    )
    return daily, signal_by_symbol


def summarize_ma_crossover(
    daily: pd.DataFrame,
    signal_by_symbol: pd.DataFrame,
    benchmark_close: pd.Series,
    start_date: str,
    end_date: str,
    fast_window: int,
    slow_window: int,
    transaction_cost_bps: float,
) -> pd.DataFrame:
    returns = pd.Series(daily["net_return"].to_numpy(dtype=float), index=pd.to_datetime(daily["date"]))
    nav = pd.Series(daily["nav"].to_numpy(dtype=float), index=returns.index)
    bench = benchmark_close.sort_index().reindex(returns.index).ffill()
    bench_ret = bench.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    bench_nav = (1.0 + bench_ret).cumprod()

    total_return = float(nav.iloc[-1] - 1.0)
    bench_total_return = float(bench_nav.iloc[-1] - 1.0)
    active = returns - bench_ret

    summary = pd.DataFrame(
        [
            {
                "start_date": start_date,
                "end_date": end_date,
                "fast_window": int(fast_window),
                "slow_window": int(slow_window),
                "transaction_cost_bps": float(transaction_cost_bps),
                "symbols_with_prices": int(signal_by_symbol.shape[0]),
                "days_tested": int(daily.shape[0]),
                "average_active_names": float(daily["active_names"].mean()),
                "average_active_ratio": float(daily["active_names"].mean() / max(signal_by_symbol.shape[0], 1)),
                "total_buy_signals": int(daily["buy_signals"].sum()),
                "total_sell_signals": int(daily["sell_signals"].sum()),
                "average_turnover": float(daily["turnover"].mean()),
                "total_cost_drag": float(daily["cost"].sum()),
                "total_return": total_return,
                "cagr": _annualized_return(total_return, int(daily.shape[0])),
                "annualized_volatility": float(returns.std(ddof=0) * np.sqrt(252.0)),
                "sharpe": _sharpe(returns),
                "max_drawdown": _max_drawdown(nav),
                "benchmark_total_return": bench_total_return,
                "benchmark_cagr": _annualized_return(bench_total_return, int(daily.shape[0])),
                "benchmark_sharpe": _sharpe(bench_ret),
                "benchmark_max_drawdown": _max_drawdown(bench_nav),
                "excess_total_return": total_return - bench_total_return,
                "tracking_error": float(active.std(ddof=0) * np.sqrt(252.0)),
                "information_ratio": _sharpe(active),
            }
        ]
    )
    return summary


def main() -> None:
    args = parse_args()
    if int(args.slow_window) <= int(args.fast_window):
        raise ValueError("slow_window must be greater than fast_window")

    params = {
        "script": "ma_crossover_sp500",
        "start_date": str(args.start_date),
        "end_date": str(args.end_date),
        "universe_source": str(args.universe_source),
        "universe_size": int(args.universe_size),
        "fast_window": int(args.fast_window),
        "slow_window": int(args.slow_window),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "benchmark_symbol": str(args.benchmark_symbol).upper(),
    }
    run_manager = ResearchRunManager(
        out_dir=Path(args.out_dir),
        params=params,
        run_tag=args.run_tag,
        tag_prefix="ma_cross_sp500",
    )
    run_dir = run_manager.run_dir()

    loader = LocalParquetDataLoader(
        data_root=Path(args.data_root),
        symbol_file=Path(args.symbol_file),
        universe_snapshot_dir=Path(args.snapshot_dir),
    )
    benchmark = str(args.benchmark_symbol).upper()
    symbols = loader.load_symbols(
        universe_source=str(args.universe_source),
        portfolio_universe=[],
        portfolio_universe_size=int(args.universe_size),
        benchmark_symbol=benchmark,
        fallback_symbol=str(args.fallback_symbol).upper(),
        asof_date=str(args.end_date),
    )
    symbols = [s for s in symbols if s.upper() != benchmark]

    warmup_days = int(args.slow_window) * 3
    load_start = (pd.Timestamp(args.start_date) - pd.Timedelta(days=warmup_days)).strftime("%Y-%m-%d")
    close = loader.load_close_matrix(symbols, load_start, str(args.end_date)).sort_index()
    close_eval = close[(close.index >= pd.Timestamp(args.start_date)) & (close.index <= pd.Timestamp(args.end_date))]
    if close_eval.empty:
        raise ValueError("No close data in evaluation window.")

    benchmark_close = loader.load_symbol_series(
        benchmark,
        str(args.start_date),
        str(args.end_date),
        field_candidates=["Adj Close", "Close"],
    )
    daily, signal_by_symbol = build_ma_crossover_portfolio(
        close=close,
        fast_window=int(args.fast_window),
        slow_window=int(args.slow_window),
        transaction_cost_bps=float(args.transaction_cost_bps),
        evaluation_start=str(args.start_date),
        evaluation_end=str(args.end_date),
    )
    summary = summarize_ma_crossover(
        daily=daily,
        signal_by_symbol=signal_by_symbol,
        benchmark_close=benchmark_close,
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        fast_window=int(args.fast_window),
        slow_window=int(args.slow_window),
        transaction_cost_bps=float(args.transaction_cost_bps),
    )

    summary_path = run_dir / "summary.csv"
    daily_path = run_dir / "daily.csv"
    signal_path = run_dir / "signal_by_symbol.csv"
    summary.to_csv(summary_path, index=False)
    daily.to_csv(daily_path, index=False)
    signal_by_symbol.to_csv(signal_path, index=False)

    params_path = run_manager.write_params(
        extra={
            "run_dir": str(run_dir),
            "load_start": load_start,
            "symbols_loaded": int(close_eval.shape[1]),
            "first_signal_date": str(pd.to_datetime(daily["date"]).min().date()),
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "daily_csv": str(daily_path),
            "signal_by_symbol_csv": str(signal_path),
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] summary: {summary_path}")
    print(f"[ok] daily: {daily_path}")
    print(f"[ok] signal by symbol: {signal_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
