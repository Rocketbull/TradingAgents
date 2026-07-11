from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from activeportfolio.dataflows.market_data_store import load_history_window
from research.common.run_manager import ResearchRunManager


DEFAULT_CANDIDATES = [
    "SPY",
    "QQQ",
    "TQQQ",
    "RSP",
    "IWM",
    "DIA",
    "XLK",
    "XLF",
    "XLY",
    "XLP",
    "XLU",
    "XLV",
    "XLE",
    "XLI",
    "XLB",
    "XLRE",
    "TLT",
    "IEF",
    "SHY",
    "HYG",
    "LQD",
    "GLD",
    "UUP",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fit long-only ETF sleeves to a saved stock-baseline return stream using "
            "local ETF history and expanding walk-forward validation."
        )
    )
    parser.add_argument(
        "--baseline-run-dir",
        default="eval_results/backtest/current_baseline_spy_offset_minus2_20260627",
        help="Directory containing rebalance_log.jsonl and optionally summary.json.",
    )
    parser.add_argument("--data-dir", default="data/market", help="Local market data root.")
    parser.add_argument("--output-dir", default="research/output", help="Research output root.")
    parser.add_argument("--run-tag", default=None, help="Optional output run tag.")
    parser.add_argument(
        "--candidates",
        default=",".join(DEFAULT_CANDIDATES),
        help="Comma-separated ETF candidate list.",
    )
    parser.add_argument(
        "--top-k",
        default="3,5,8",
        help="Comma-separated sleeve sizes for greedy selection.",
    )
    parser.add_argument(
        "--min-train-periods",
        type=int,
        default=18,
        help="Initial expanding training window length for walk-forward tests.",
    )
    parser.add_argument(
        "--ridge",
        type=float,
        default=1e-4,
        help="Small L2 penalty on weights in the regression objective.",
    )
    parser.add_argument(
        "--max-weight",
        type=float,
        default=1.0,
        help="Per-ETF upper bound for fitted long-only weights.",
    )
    return parser.parse_args()


def _load_rebalance_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    rows = [r for r in rows if r.get("trade_date") and r.get("next_date")]
    if not rows:
        raise ValueError(f"No period rebalance rows found in {path}")
    return rows


def _price_asof(prices: pd.DataFrame, symbol: str, date: str) -> float:
    loc = prices.index.searchsorted(pd.Timestamp(date), side="right") - 1
    if loc < 0:
        return float("nan")
    value = float(prices.iloc[loc][symbol])
    return value if np.isfinite(value) and value > 0.0 else float("nan")


def _load_prices(
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
    return prices.sort_index().ffill(), missing


def build_period_returns(
    rows: list[dict[str, Any]],
    candidate_symbols: list[str],
    data_dir: str,
) -> tuple[pd.DataFrame, list[str]]:
    start_date = min(str(r["trade_date"]) for r in rows)
    end_date = max(str(r["next_date"]) for r in rows)
    prices, missing = _load_prices(candidate_symbols, start_date, end_date, data_dir)

    records: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        rec: dict[str, Any] = {
            "period_index": idx,
            "trade_date": row["trade_date"],
            "next_date": row["next_date"],
            "baseline_return": float(row.get("portfolio_return", np.nan)),
            "benchmark_return": float(row.get("benchmark_return", np.nan)),
            "baseline_orders_count": int(row.get("orders_count", 0)),
        }
        for symbol in prices.columns:
            start_price = _price_asof(prices, symbol, str(row["trade_date"]))
            end_price = _price_asof(prices, symbol, str(row["next_date"]))
            rec[symbol] = end_price / start_price - 1.0 if np.isfinite(start_price + end_price) else np.nan
        records.append(rec)

    df = pd.DataFrame(records)
    available = [s for s in prices.columns if df[s].notna().all()]
    return df[["period_index", "trade_date", "next_date", "baseline_return", "benchmark_return", "baseline_orders_count", *available]], missing


def _fit_long_only_weights(
    x: np.ndarray,
    y: np.ndarray,
    ridge: float,
    max_weight: float,
) -> np.ndarray:
    n = int(x.shape[1])
    if n == 0:
        raise ValueError("Need at least one candidate ETF.")
    init = np.full(n, 1.0 / n)
    bounds = [(0.0, float(max_weight)) for _ in range(n)]
    constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]

    def objective(w: np.ndarray) -> float:
        residual = x @ w - y
        return float(np.mean(residual * residual) + float(ridge) * np.sum(w * w))

    result = minimize(objective, init, method="SLSQP", bounds=bounds, constraints=constraints)
    if not result.success:
        raise RuntimeError(f"Weight fit failed: {result.message}")
    w = np.clip(np.asarray(result.x, dtype=float), 0.0, float(max_weight))
    total = float(w.sum())
    if total <= 0.0:
        return init
    return w / total


def _score_fit(x: np.ndarray, y: np.ndarray, weights: np.ndarray, ridge: float) -> float:
    residual = x @ weights - y
    return float(np.mean(residual * residual) + float(ridge) * np.sum(weights * weights))


def greedy_select(
    x: np.ndarray,
    y: np.ndarray,
    symbols: list[str],
    top_k: int,
    ridge: float,
    max_weight: float,
) -> tuple[list[str], np.ndarray]:
    selected: list[int] = []
    remaining = list(range(len(symbols)))
    for _ in range(min(int(top_k), len(symbols))):
        best: tuple[float, int, np.ndarray] | None = None
        for idx in remaining:
            trial = selected + [idx]
            weights = _fit_long_only_weights(x[:, trial], y, ridge=ridge, max_weight=max_weight)
            score = _score_fit(x[:, trial], y, weights, ridge=ridge)
            if best is None or score < best[0]:
                best = (score, idx, weights)
        if best is None:
            break
        selected.append(best[1])
        remaining.remove(best[1])
    final_weights = _fit_long_only_weights(x[:, selected], y, ridge=ridge, max_weight=max_weight)
    return [symbols[i] for i in selected], final_weights


def summarize_returns(periods: pd.DataFrame, return_col: str) -> dict[str, float]:
    diff = periods[return_col] - periods["baseline_return"]
    return {
        "periods": int(periods.shape[0]),
        "baseline_total_return": float((1.0 + periods["baseline_return"]).prod() - 1.0),
        "etf_total_return": float((1.0 + periods[return_col]).prod() - 1.0),
        "return_difference": float((1.0 + periods[return_col]).prod() - (1.0 + periods["baseline_return"]).prod()),
        "annualized_monthly_tracking_error_vs_baseline": float(diff.std(ddof=1) * np.sqrt(12.0)) if len(diff) > 1 else float("nan"),
        "mean_period_difference": float(diff.mean()),
        "mean_abs_period_difference": float(diff.abs().mean()),
        "correlation_to_baseline": float(periods[[return_col, "baseline_return"]].corr().iloc[0, 1]),
    }


def build_static_fit(
    period_returns: pd.DataFrame,
    symbols: list[str],
    top_k: int,
    ridge: float,
    max_weight: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    x = period_returns[symbols].to_numpy(dtype=float)
    y = period_returns["baseline_return"].to_numpy(dtype=float)
    selected, weights = greedy_select(x, y, symbols, top_k=top_k, ridge=ridge, max_weight=max_weight)
    fitted = period_returns[["period_index", "trade_date", "next_date", "baseline_return", "benchmark_return", "baseline_orders_count"]].copy()
    fitted["etf_return"] = period_returns[selected].to_numpy(dtype=float) @ weights
    fitted["active_return_vs_baseline"] = fitted["etf_return"] - fitted["baseline_return"]
    weight_df = pd.DataFrame({"symbol": selected, "weight": weights}).sort_values("weight", ascending=False)
    summary = summarize_returns(fitted, "etf_return")
    summary.update({"top_k": int(top_k), "selected": selected, "weights": dict(zip(selected, map(float, weights)))})
    return fitted, weight_df, summary


def build_walk_forward_fit(
    period_returns: pd.DataFrame,
    symbols: list[str],
    top_k: int,
    min_train_periods: int,
    ridge: float,
    max_weight: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []
    previous_weights: dict[str, float] = {}

    for test_pos in range(int(min_train_periods), period_returns.shape[0]):
        train = period_returns.iloc[:test_pos]
        test = period_returns.iloc[test_pos]
        x_train = train[symbols].to_numpy(dtype=float)
        y_train = train["baseline_return"].to_numpy(dtype=float)
        selected, weights = greedy_select(
            x_train,
            y_train,
            symbols,
            top_k=top_k,
            ridge=ridge,
            max_weight=max_weight,
        )
        current_weights = dict(zip(selected, map(float, weights)))
        etf_return = float(test[selected].to_numpy(dtype=float) @ weights)
        turnover = sum(
            abs(previous_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
            for symbol in set(previous_weights) | set(current_weights)
        )
        order_proxy = sum(
            1
            for symbol in set(previous_weights) | set(current_weights)
            if abs(previous_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0)) > 1e-6
        )
        rows.append(
            {
                "period_index": int(test["period_index"]),
                "trade_date": test["trade_date"],
                "next_date": test["next_date"],
                "baseline_return": float(test["baseline_return"]),
                "benchmark_return": float(test["benchmark_return"]),
                "baseline_orders_count": int(test["baseline_orders_count"]),
                "etf_return": etf_return,
                "active_return_vs_baseline": etf_return - float(test["baseline_return"]),
                "selected_count": len(selected),
                "etf_orders_count_proxy": order_proxy,
                "etf_turnover_proxy": turnover,
            }
        )
        for symbol, weight in current_weights.items():
            weight_rows.append(
                {
                    "period_index": int(test["period_index"]),
                    "trade_date": test["trade_date"],
                    "symbol": symbol,
                    "weight": weight,
                }
            )
        previous_weights = current_weights

    fitted = pd.DataFrame(rows)
    weights_df = pd.DataFrame(weight_rows)
    summary = summarize_returns(fitted, "etf_return")
    summary.update(
        {
            "top_k": int(top_k),
            "min_train_periods": int(min_train_periods),
            "mean_etf_orders_count_proxy": float(fitted["etf_orders_count_proxy"].mean()),
            "mean_etf_turnover_proxy": float(fitted["etf_turnover_proxy"].mean()),
            "mean_baseline_orders_count": float(fitted["baseline_orders_count"].mean()),
            "latest_weights": (
                weights_df[weights_df["period_index"] == weights_df["period_index"].max()]
                .sort_values("weight", ascending=False)[["symbol", "weight"]]
                .to_dict(orient="records")
                if not weights_df.empty
                else []
            ),
        }
    )
    return fitted, weights_df, summary


def main() -> None:
    args = parse_args()
    candidates = [s.strip().upper() for s in args.candidates.split(",") if s.strip()]
    top_ks = [int(x.strip()) for x in args.top_k.split(",") if x.strip()]
    rows = _load_rebalance_rows(Path(args.baseline_run_dir) / "rebalance_log.jsonl")
    period_returns, missing = build_period_returns(rows, candidates, args.data_dir)
    available_symbols = [s for s in candidates if s in period_returns.columns]
    if len(available_symbols) < 2:
        raise ValueError("Need at least two available ETF candidates.")

    params = {
        "baseline_run_dir": args.baseline_run_dir,
        "data_dir": args.data_dir,
        "candidates": candidates,
        "available_symbols": available_symbols,
        "missing_symbols": missing,
        "top_k": top_ks,
        "min_train_periods": args.min_train_periods,
        "ridge": args.ridge,
        "max_weight": args.max_weight,
        "start_date": str(period_returns["trade_date"].min()),
        "end_date": str(period_returns["next_date"].max()),
    }
    manager = ResearchRunManager(
        out_dir=Path(args.output_dir),
        params=params,
        run_tag=args.run_tag,
        tag_prefix="etf_return_regression_approx",
    )
    run_dir = manager.run_dir()
    period_returns.to_csv(run_dir / "period_returns.csv", index=False)

    summaries: dict[str, Any] = {"missing_symbols": missing, "available_symbols": available_symbols}
    artifacts: dict[str, str | None] = {"period_returns": str(run_dir / "period_returns.csv")}
    for top_k in top_ks:
        static_periods, static_weights, static_summary = build_static_fit(
            period_returns,
            available_symbols,
            top_k=top_k,
            ridge=args.ridge,
            max_weight=args.max_weight,
        )
        static_periods.to_csv(run_dir / f"static_top{top_k}_periods.csv", index=False)
        static_weights.to_csv(run_dir / f"static_top{top_k}_weights.csv", index=False)
        summaries[f"static_top{top_k}"] = static_summary
        artifacts[f"static_top{top_k}_periods"] = str(run_dir / f"static_top{top_k}_periods.csv")
        artifacts[f"static_top{top_k}_weights"] = str(run_dir / f"static_top{top_k}_weights.csv")

        wf_periods, wf_weights, wf_summary = build_walk_forward_fit(
            period_returns,
            available_symbols,
            top_k=top_k,
            min_train_periods=args.min_train_periods,
            ridge=args.ridge,
            max_weight=args.max_weight,
        )
        wf_periods.to_csv(run_dir / f"walk_forward_top{top_k}_periods.csv", index=False)
        wf_weights.to_csv(run_dir / f"walk_forward_top{top_k}_weights.csv", index=False)
        summaries[f"walk_forward_top{top_k}"] = wf_summary
        artifacts[f"walk_forward_top{top_k}_periods"] = str(run_dir / f"walk_forward_top{top_k}_periods.csv")
        artifacts[f"walk_forward_top{top_k}_weights"] = str(run_dir / f"walk_forward_top{top_k}_weights.csv")

    (run_dir / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    manager.write_params(extra={"summary": summaries})
    manager.write_manifest(artifacts={**artifacts, "summary": str(run_dir / "summary.json")}, extra={"summary": summaries})
    print(json.dumps({"run_dir": str(run_dir), "summary": summaries}, indent=2))


if __name__ == "__main__":
    main()
