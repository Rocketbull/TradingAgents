from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from activeportfolio.backtest import BacktestEngine
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
        description="Run historical backtest using the robust backtest engine."
    )
    parser.add_argument(
        "--config-json",
        default=None,
        help="Optional JSON file with full backtest/engine config overrides.",
    )
    parser.add_argument("--start-date", default=None, help="Backtest start date YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Backtest end date YYYY-MM-DD.")
    parser.add_argument(
        "--rebalance-frequency",
        default=None,
        choices=["daily", "weekly", "monthly"],
        help="Rebalance cadence.",
    )
    parser.add_argument(
        "--universe-source",
        default=None,
        choices=["single_symbol", "config_list", "sp500_file", "sp500_snapshot"],
        help="Universe source strategy.",
    )
    parser.add_argument(
        "--universe-size",
        type=int,
        default=None,
        help="Number of symbols to use from symbol file when using sp500_file.",
    )
    parser.add_argument(
        "--symbol-file",
        default=None,
        help="Path to symbol list file.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=None,
        help="Path to dated SP500 snapshot files (sp500_membership_YYYY-MM-DD.csv).",
    )
    parser.add_argument(
        "--benchmark-symbol",
        default=None,
        help="Benchmark symbol.",
    )
    parser.add_argument(
        "--max-weight",
        type=float,
        default=None,
        help="Maximum position weight.",
    )
    parser.add_argument(
        "--turnover-limit",
        type=float,
        default=None,
        help="Turnover cap per rebalance.",
    )
    parser.add_argument(
        "--risk-aversion",
        type=float,
        default=None,
        help="Risk aversion parameter for optimizer.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=None,
        help="Transaction cost model in bps.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Directory to store backtest artifacts.",
    )
    parser.add_argument(
        "--alpha-profile",
        default=None,
        help="Optional named alpha profile to apply before backtest execution.",
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
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable dynamic liquidity filter by rolling median dollar volume.",
    )
    parser.add_argument(
        "--liquidity-top-n",
        type=int,
        default=None,
        help="Top N liquid symbols to keep each rebalance when filter is enabled.",
    )
    parser.add_argument(
        "--liquidity-lookback-days",
        type=int,
        default=None,
        help="Lookback days for median dollar volume liquidity ranking.",
    )
    parser.add_argument(
        "--monthly-rebalance-offset-days",
        type=int,
        default=None,
        help="Trading-day offset from month-end for monthly rebalances. Negative is before month-end.",
    )
    args = parser.parse_args()
    if args.start_date is None and args.end_date is None and args.config_json is None:
        parser.error("--start-date and --end-date are required unless provided via --config-json.")
    return args


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    config = DEFAULT_CONFIG.copy()
    config.update(load_config_json(args.config_json))
    config["portfolio_mode"] = True

    cli_updates = {
        "backtest_start_date": args.start_date,
        "backtest_end_date": args.end_date,
        "backtest_output_dir": args.out_dir,
        "rebalance_frequency": args.rebalance_frequency,
        "universe_source": args.universe_source,
        "portfolio_universe_size": args.universe_size,
        "symbol_file": args.symbol_file,
        "universe_snapshot_dir": args.snapshot_dir,
        "benchmark_symbol": args.benchmark_symbol.upper() if args.benchmark_symbol else None,
        "max_weight": args.max_weight,
        "turnover_limit": args.turnover_limit,
        "risk_aversion": args.risk_aversion,
        "transaction_cost_bps": args.transaction_cost_bps,
        "dynamic_liquidity_filter": args.dynamic_liquidity_filter,
        "liquidity_top_n": args.liquidity_top_n,
        "liquidity_lookback_days": args.liquidity_lookback_days,
        "monthly_rebalance_offset_days": args.monthly_rebalance_offset_days,
        "alpha_profile": getattr(args, "alpha_profile", None),
    }
    config.update({k: v for k, v in cli_updates.items() if v is not None})

    if args.alpha_signal:
        config["alpha_signals"] = [str(s) for s in args.alpha_signal]

    if not config.get("backtest_start_date") or not config.get("backtest_end_date"):
        raise ValueError(
            "backtest_start_date and backtest_end_date are required via CLI or --config-json"
        )
    return config


def main() -> None:
    args = parse_args()
    config = build_config(args)

    engine = BacktestEngine(config)
    result = engine.run(fallback_symbol=str(config.get("benchmark_symbol", "SPY")).upper())
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
