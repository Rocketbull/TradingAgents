from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.backtest_position_report import latest_trade_date, resolve_backtest_root, resolve_run_dir


def load_summary(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))


def load_rebalance_log(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(run_dir / "rebalance_log.jsonl", "r", encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def load_equity_curve(run_dir: Path) -> pd.DataFrame | None:
    path = run_dir / "equity_curve.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


def load_config_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config JSON must be an object: {path}")
    return payload


def default_baseline_family(config_path: Path) -> str:
    config = load_config_json(config_path)
    output_dir = str(config.get("backtest_output_dir", "")).strip()
    if not output_dir:
        raise ValueError(f"backtest_output_dir missing in {config_path}")
    return Path(output_dir).name


def _is_baseline_family_dir(path: Path, family_name: str) -> bool:
    pattern = (
        rf"^{re.escape(family_name)}"
        rf"(?:_(?:\d{{8}}|\d{{4}}-\d{{2}}-\d{{2}})(?:_[A-Za-z0-9-]+)*)?$"
    )
    return bool(re.fullmatch(pattern, path.name))


def resolve_latest_default_baseline_run(
    backtest_root: Path,
    baseline_config_path: Path,
) -> Path:
    family_name = default_baseline_family(baseline_config_path)
    candidates: list[dict[str, Any]] = []

    for path in backtest_root.iterdir():
        if not path.is_dir():
            continue
        if not _is_baseline_family_dir(path, family_name):
            continue
        summary_path = path / "summary.json"
        weights_path = path / "weights_history.csv"
        rebalance_log_path = path / "rebalance_log.jsonl"
        if not (summary_path.exists() and weights_path.exists() and rebalance_log_path.exists()):
            continue
        summary = load_summary(path)
        summary_end = str(summary.get("end_date", ""))
        is_mutable_alias = path.name == family_name
        is_terminal = path.name.endswith("_terminal")
        has_daily_market_value = (path / "daily_market_value.csv").exists()
        candidates.append(
            {
                "path": path,
                "summary_end": summary_end,
                "latest_trade_date": latest_trade_date(path).strftime("%Y-%m-%d"),
                "is_mutable_alias": is_mutable_alias,
                "is_terminal": is_terminal,
                "has_daily_market_value": has_daily_market_value,
            }
        )

    if not candidates:
        raise FileNotFoundError(
            f"No saved runs found for baseline family '{family_name}' under {backtest_root}"
        )

    candidates.sort(
        key=lambda row: (
            row["summary_end"],
            row["latest_trade_date"],
            int(not row["is_mutable_alias"]),
            int(row["has_daily_market_value"]),
            int(not row["is_terminal"]),
        ),
        reverse=True,
    )
    return Path(candidates[0]["path"])


def _sorted_weight_pairs(weights: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    ranked = [
        {"symbol": str(symbol), "weight": float(weight)}
        for symbol, weight in weights.items()
        if abs(float(weight)) >= 1e-4
    ]
    ranked.sort(key=lambda row: row["weight"], reverse=True)
    return ranked[:limit]


def _weight_deltas(
    previous_weights: dict[str, Any],
    current_weights: dict[str, Any],
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deltas: list[dict[str, Any]] = []
    for symbol in sorted(set(previous_weights) | set(current_weights)):
        previous = float(previous_weights.get(symbol, 0.0))
        current = float(current_weights.get(symbol, 0.0))
        delta = current - previous
        if abs(delta) < 1e-4:
            continue
        deltas.append(
            {
                "symbol": str(symbol),
                "previous_weight": previous,
                "current_weight": current,
                "delta": delta,
            }
        )
    adds = [row for row in deltas if row["delta"] > 0]
    trims = [row for row in deltas if row["delta"] < 0]
    adds.sort(key=lambda row: row["delta"], reverse=True)
    trims.sort(key=lambda row: row["delta"])
    return adds[:limit], trims[:limit]


def build_monthly_commentary_context(run_dir: Path) -> dict[str, Any]:
    summary = load_summary(run_dir)
    rebalance_log = load_rebalance_log(run_dir)
    equity_curve = load_equity_curve(run_dir)
    if len(rebalance_log) < 2:
        raise ValueError("Need at least two rebalance snapshots to build monthly commentary context.")

    current_row = rebalance_log[-1]
    is_terminal_snapshot = (
        int(current_row.get("terminal_snapshot", 0)) == 1
        or str(current_row.get("trade_date", "")) == str(current_row.get("next_date", ""))
    )
    if is_terminal_snapshot and len(rebalance_log) >= 2:
        performance_row = rebalance_log[-2]
    else:
        performance_row = current_row

    if performance_row is current_row:
        previous_row = rebalance_log[-2]
    else:
        previous_row = performance_row

    equity_perf_row: dict[str, Any] | None = None
    if equity_curve is not None and not equity_curve.empty:
        if "terminal_snapshot" in equity_curve.columns and int(equity_curve.iloc[-1].get("terminal_snapshot", 0)) == 1:
            if len(equity_curve) >= 2:
                equity_perf_row = equity_curve.iloc[-2].to_dict()
        else:
            equity_perf_row = equity_curve.iloc[-1].to_dict()

    portfolio_return = performance_row.get("portfolio_return")
    benchmark_return = performance_row.get("benchmark_return")
    active_return = performance_row.get("active_return")
    if (portfolio_return is None or benchmark_return is None) and equity_perf_row is not None:
        portfolio_return = equity_perf_row.get("portfolio_return", 0.0)
        benchmark_return = equity_perf_row.get("benchmark_return", 0.0)
        active_return = float(portfolio_return) - float(benchmark_return)

    previous_weights = dict(previous_row.get("target_weights", {}))
    current_weights = dict(current_row.get("target_weights", {}))
    top_adds, top_trims = _weight_deltas(previous_weights, current_weights, limit=10)

    initial_capital = float(summary.get("initial_capital", 0.0))
    nav_before_rebalance = float(current_row.get("nav_before", 0.0))
    since_inception_return = (
        nav_before_rebalance / initial_capital - 1.0
        if initial_capital > 0
        else 0.0
    )

    return {
        "run_dir": str(run_dir),
        "benchmark_symbol": str(summary.get("benchmark_symbol", "")).upper(),
        "analysis_date": str(current_row.get("trade_date", "")),
        "period_start": str(performance_row.get("trade_date", "")),
        "period_end": str(current_row.get("trade_date", "")),
        "performance": {
            "portfolio_return": float(portfolio_return or 0.0),
            "benchmark_return": float(benchmark_return or 0.0),
            "active_return": float(active_return or 0.0),
            "nav_start_after_rebalance": float(performance_row.get("nav_after_costs", 0.0)),
            "nav_before_current_rebalance": nav_before_rebalance,
            "nav_after_current_rebalance": float(current_row.get("nav_after_costs", nav_before_rebalance)),
            "rebalance_cost": float(current_row.get("cost", 0.0)),
            "since_inception_return": since_inception_return,
            "total_return": float(summary.get("total_return", 0.0)),
            "sharpe": float(summary.get("sharpe", 0.0)),
            "max_drawdown": float(summary.get("max_drawdown", 0.0)),
        },
        "rebalance": {
            "orders_count": int(current_row.get("orders_count", 0)),
            "turnover": float(current_row.get("turnover", 0.0)),
            "top_adds": top_adds,
            "top_trims": top_trims,
            "top_holdings_after_rebalance": _sorted_weight_pairs(current_weights, limit=10),
            "signal_emphasis": _sorted_weight_pairs(dict(current_row.get("alpha_weights", {})), limit=5),
        },
        "regime": dict(current_row.get("regime", {})),
        "portfolio_metrics": dict(current_row.get("portfolio_metrics", {})),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract latest one-month backtest context for GenAI investor commentary."
    )
    parser.add_argument("--run-dir", default=None, help="Optional backtest run directory.")
    parser.add_argument(
        "--backtest-root",
        default=str(resolve_backtest_root()),
        help="Backtest root used when --run-dir is omitted.",
    )
    parser.add_argument(
        "--baseline-config-json",
        default="research/configs/backtest_current_baseline.json",
        help="Canonical production baseline config used to resolve the latest baseline-family run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.run_dir:
        run_dir = resolve_run_dir(args.run_dir, args.backtest_root)
    else:
        run_dir = resolve_latest_default_baseline_run(
            backtest_root=Path(args.backtest_root),
            baseline_config_path=Path(args.baseline_config_json),
        )
    context = _json_safe(build_monthly_commentary_context(run_dir))
    print(json.dumps(context, indent=2))


if __name__ == "__main__":
    main()
