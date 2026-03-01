from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tradingagents.backtest import BacktestEngine
from tradingagents.default_config import DEFAULT_CONFIG


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run historical backtest using the robust backtest engine."
    )
    parser.add_argument("--start-date", required=True, help="Backtest start date YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="Backtest end date YYYY-MM-DD.")
    parser.add_argument(
        "--rebalance-frequency",
        default="weekly",
        choices=["daily", "weekly", "monthly"],
        help="Rebalance cadence.",
    )
    parser.add_argument(
        "--universe-source",
        default="sp500_file",
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
        help="Universe source strategy.",
    )
    parser.add_argument(
        "--universe-size",
        type=int,
        default=50,
        help="Number of symbols to use from symbol file when using sp500_file.",
    )
    parser.add_argument(
        "--symbol-file",
        default="data/universe/sp500/current/sp500_symbols.txt",
        help="Path to symbol list file.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="data/universe/sp500/snapshots",
        help="Path to dated SP500 snapshot files (sp500_membership_YYYY-MM-DD.csv).",
    )
    parser.add_argument(
        "--benchmark-symbol",
        default="SPY",
        help="Benchmark symbol.",
    )
    parser.add_argument(
        "--max-weight",
        type=float,
        default=0.05,
        help="Maximum position weight.",
    )
    parser.add_argument(
        "--turnover-limit",
        type=float,
        default=0.20,
        help="Turnover cap per rebalance.",
    )
    parser.add_argument(
        "--risk-aversion",
        type=float,
        default=3.0,
        help="Risk aversion parameter for optimizer.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=5.0,
        help="Transaction cost model in bps.",
    )
    parser.add_argument(
        "--out-dir",
        default="eval_results/backtest/run_backtest",
        help="Directory to store backtest artifacts.",
    )
    parser.add_argument(
        "--alpha-signal",
        action="append",
        default=[],
        help=(
            "Alpha signal name to use (repeatable). "
            "When set, overrides config alpha_signals and can force single-alpha runs."
        ),
    )
    parser.add_argument(
        "--dynamic-liquidity-filter",
        action="store_true",
        help="Enable dynamic liquidity filter by rolling median dollar volume.",
    )
    parser.add_argument(
        "--liquidity-top-n",
        type=int,
        default=100,
        help="Top N liquid symbols to keep each rebalance when filter is enabled.",
    )
    parser.add_argument(
        "--liquidity-lookback-days",
        type=int,
        default=60,
        help="Lookback days for median dollar volume liquidity ranking.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "portfolio_mode": True,
            "backtest_start_date": args.start_date,
            "backtest_end_date": args.end_date,
            "backtest_output_dir": args.out_dir,
            "rebalance_frequency": args.rebalance_frequency,
            "universe_source": args.universe_source,
            "portfolio_universe_size": args.universe_size,
            "symbol_file": args.symbol_file,
            "universe_snapshot_dir": args.snapshot_dir,
            "benchmark_symbol": args.benchmark_symbol.upper(),
            "max_weight": args.max_weight,
            "turnover_limit": args.turnover_limit,
            "risk_aversion": args.risk_aversion,
            "transaction_cost_bps": args.transaction_cost_bps,
            "dynamic_liquidity_filter": args.dynamic_liquidity_filter,
            "liquidity_top_n": args.liquidity_top_n,
            "liquidity_lookback_days": args.liquidity_lookback_days,
        }
    )
    if args.alpha_signal:
        config["alpha_signals"] = [str(s) for s in args.alpha_signal]

    engine = BacktestEngine(config)
    result = engine.run(fallback_symbol=args.benchmark_symbol.upper())
    summary = result["summary"]
    out_dir = Path(result["output_dir"])

    print("[ok] backtest completed")
    print(f"[ok] output_dir: {out_dir}")
    print(f"[ok] rebalance_points: {summary['rebalance_points']}")
    print(f"[ok] total_return: {summary['total_return']:.6f}")
    print(f"[ok] sharpe: {summary['sharpe']:.6f}")

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
