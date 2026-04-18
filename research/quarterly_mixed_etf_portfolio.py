from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.common.run_manager import ResearchRunManager
from tradingagents.dataflows.market_data_store import load_history_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Research a two-asset portfolio with quarterly rebalancing."
    )
    parser.add_argument("--symbol-a", default="XLK", help="First symbol in the portfolio.")
    parser.add_argument("--symbol-b", default="XLE", help="Second symbol in the portfolio.")
    parser.add_argument("--weight-a", type=float, required=True, help="Target weight for symbol-a, in [0,1].")
    parser.add_argument("--weight-b", type=float, required=True, help="Target weight for symbol-b, in [0,1].")
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD.")
    parser.add_argument("--data-dir", default="data/market", help="Parquet root directory.")
    parser.add_argument("--output-dir", default="research/output", help="Research output directory.")
    parser.add_argument("--run-tag", default=None, help="Optional run tag.")
    parser.add_argument(
        "--config-json",
        default=None,
        help="Optional config JSON path recorded in the run manifest.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=0.0,
        help="Per-side transaction cost in basis points, applied on rebalance notional turnover.",
    )
    return parser.parse_args()


def _annualized_return(total_return: float, periods: int) -> float:
    if periods <= 0:
        return float("nan")
    growth = 1.0 + float(total_return)
    if growth <= 0:
        return float("nan")
    return growth ** (252.0 / float(periods)) - 1.0


def _annualized_volatility(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    std = float(returns.std(ddof=1))
    if not np.isfinite(std):
        return float("nan")
    return std * np.sqrt(252.0)


def _sharpe_ratio(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    mean = float(returns.mean())
    std = float(returns.std(ddof=1))
    if not np.isfinite(std) or std == 0.0:
        return float("nan")
    return mean / std * np.sqrt(252.0)


def _max_drawdown(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return float("nan")
    running_peak = equity_curve.cummax()
    drawdown = equity_curve / running_peak - 1.0
    return float(drawdown.min())


def _load_price_series(symbol: str, start_date: str, end_date: str, data_dir: str) -> pd.DataFrame:
    history = load_history_window(symbol=symbol, start_date=start_date, end_date=end_date, root_dir=data_dir).copy()
    history["Date"] = pd.to_datetime(history["Date"])
    price_col = "Adj Close" if "Adj Close" in history.columns else "Close"
    history[price_col] = pd.to_numeric(history[price_col], errors="coerce")
    return history[["Date", price_col]].rename(columns={price_col: symbol.upper()}).sort_values("Date")


def build_quarterly_portfolio(
    prices: pd.DataFrame,
    symbol_a: str,
    symbol_b: str,
    weight_a: float,
    weight_b: float,
    transaction_cost_bps: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    total = float(weight_a) + float(weight_b)
    if total <= 0:
        raise ValueError("Portfolio weights must sum to a positive value.")
    weight_a = float(weight_a) / total
    weight_b = float(weight_b) / total

    df = prices.copy().sort_values("Date").reset_index(drop=True)
    df = df.rename(columns={"Date": "date"})
    df["ret_a"] = df[symbol_a].pct_change()
    df["ret_b"] = df[symbol_b].pct_change()
    df["quarter"] = df["date"].dt.to_period("Q")
    df["rebalance"] = df["quarter"] != df["quarter"].shift(1)

    per_side_cost = float(transaction_cost_bps) / 10000.0

    rows: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    w_a = weight_a
    w_b = weight_b
    equity_net = 1.0
    equity_gross = 1.0
    initial_value_a = weight_a
    initial_value_b = weight_b

    for idx, rec in df.iterrows():
        date = rec["date"]
        ret_a = float(rec["ret_a"]) if pd.notna(rec["ret_a"]) else np.nan
        ret_b = float(rec["ret_b"]) if pd.notna(rec["ret_b"]) else np.nan
        rebalance = bool(rec["rebalance"])

        if rebalance:
            turnover = abs(w_a - weight_a) + abs(w_b - weight_b)
            cost = turnover * per_side_cost
            trades.append(
                {
                    "date": date,
                    "target_weight_a": weight_a,
                    "target_weight_b": weight_b,
                    "pre_rebalance_weight_a": w_a,
                    "pre_rebalance_weight_b": w_b,
                    "turnover": turnover,
                    "cost": cost,
                }
            )
            w_a = weight_a
            w_b = weight_b
        else:
            turnover = 0.0
            cost = 0.0

        if pd.isna(ret_a) or pd.isna(ret_b):
            portfolio_gross_return = 0.0
        else:
            portfolio_gross_return = w_a * ret_a + w_b * ret_b

        portfolio_net_return = portfolio_gross_return - cost
        equity_gross *= 1.0 + portfolio_gross_return
        equity_net *= 1.0 + portfolio_net_return

        if pd.notna(ret_a) and pd.notna(ret_b):
            value_a = w_a * (1.0 + ret_a)
            value_b = w_b * (1.0 + ret_b)
            gross_nav = value_a + value_b
            w_a = value_a / gross_nav if gross_nav else 0.0
            w_b = value_b / gross_nav if gross_nav else 0.0

            initial_value_a *= 1.0 + ret_a
            initial_value_b *= 1.0 + ret_b
        buy_hold_equity = initial_value_a + initial_value_b

        rows.append(
            {
                "date": date,
                symbol_a: rec[symbol_a],
                symbol_b: rec[symbol_b],
                "ret_a": 0.0 if pd.isna(ret_a) else ret_a,
                "ret_b": 0.0 if pd.isna(ret_b) else ret_b,
                "rebalance": rebalance,
                "turnover": turnover,
                "cost": cost,
                "weight_a_end": w_a,
                "weight_b_end": w_b,
                "portfolio_gross_return": portfolio_gross_return,
                "portfolio_net_return": portfolio_net_return,
                "equity_curve_gross": equity_gross,
                "equity_curve_net": equity_net,
                "buy_hold_equity_curve": buy_hold_equity,
            }
        )

    by_date = pd.DataFrame(rows)
    by_date["drawdown_net"] = by_date["equity_curve_net"] / by_date["equity_curve_net"].cummax() - 1.0
    trade_log = pd.DataFrame(trades)
    return by_date, trade_log


def summarize_portfolio(
    by_date: pd.DataFrame,
    trade_log: pd.DataFrame,
    symbol_a: str,
    symbol_b: str,
    weight_a: float,
    weight_b: float,
    start_date: str,
    end_date: str,
    transaction_cost_bps: float,
) -> pd.DataFrame:
    net_total_return = float(by_date["equity_curve_net"].iloc[-1] - 1.0)
    gross_total_return = float(by_date["equity_curve_gross"].iloc[-1] - 1.0)
    buy_hold_return = float(by_date["buy_hold_equity_curve"].iloc[-1] - 1.0)

    return pd.DataFrame(
        [
            {
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "weight_a": weight_a,
                "weight_b": weight_b,
                "start_date": start_date,
                "end_date": end_date,
                "rebalance_frequency": "quarterly",
                "days_tested": int(by_date.shape[0]),
                "rebalance_count": int(trade_log.shape[0]),
                "gross_total_return": gross_total_return,
                "net_total_return": net_total_return,
                "net_annualized_return": _annualized_return(net_total_return, int(by_date.shape[0])),
                "net_annualized_volatility": _annualized_volatility(by_date["portfolio_net_return"]),
                "net_sharpe": _sharpe_ratio(by_date["portfolio_net_return"]),
                "net_max_drawdown": _max_drawdown(by_date["equity_curve_net"]),
                "buy_and_hold_return_same_window": buy_hold_return,
                "mean_net_return": float(by_date["portfolio_net_return"].mean()),
                "median_net_return": float(by_date["portfolio_net_return"].median()),
                "win_rate": float((by_date["portfolio_net_return"] > 0.0).mean()),
                "avg_turnover_per_rebalance": float(trade_log["turnover"].mean()) if not trade_log.empty else 0.0,
                "transaction_cost_bps_per_side": float(transaction_cost_bps),
            }
        ]
    )


def main() -> None:
    args = parse_args()
    symbol_a = str(args.symbol_a).upper()
    symbol_b = str(args.symbol_b).upper()
    params: dict[str, Any] = {
        "script": "quarterly_mixed_etf_portfolio",
        "symbol_a": symbol_a,
        "symbol_b": symbol_b,
        "weight_a": float(args.weight_a),
        "weight_b": float(args.weight_b),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "transaction_cost_bps_per_side": float(args.transaction_cost_bps),
    }
    run_manager = ResearchRunManager(
        out_dir=Path(args.output_dir),
        params=params,
        run_tag=args.run_tag,
        tag_prefix="quarterly_mix",
    )
    run_dir = run_manager.run_dir()

    price_a = _load_price_series(symbol_a, args.start_date, args.end_date, args.data_dir)
    price_b = _load_price_series(symbol_b, args.start_date, args.end_date, args.data_dir)
    prices = pd.merge(price_a, price_b, on="Date", how="inner").dropna().sort_values("Date")
    if prices.empty:
        raise ValueError("No overlapping history found for the requested symbols and date window.")

    by_date, trade_log = build_quarterly_portfolio(
        prices=prices,
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        weight_a=float(args.weight_a),
        weight_b=float(args.weight_b),
        transaction_cost_bps=float(args.transaction_cost_bps),
    )
    summary = summarize_portfolio(
        by_date=by_date,
        trade_log=trade_log,
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        weight_a=float(args.weight_a),
        weight_b=float(args.weight_b),
        start_date=args.start_date,
        end_date=args.end_date,
        transaction_cost_bps=float(args.transaction_cost_bps),
    )

    summary_path = run_dir / "summary.csv"
    by_date_path = run_dir / "by_date.csv"
    by_trade_path = run_dir / "by_trade.csv"
    summary.to_csv(summary_path, index=False)
    by_date.to_csv(by_date_path, index=False)
    trade_log.to_csv(by_trade_path, index=False)

    params_path = run_manager.write_params(
        extra={
            "net_total_return": float(summary.iloc[0]["net_total_return"]),
            "net_sharpe": float(summary.iloc[0]["net_sharpe"]),
            "rebalance_count": int(summary.iloc[0]["rebalance_count"]),
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "by_date_csv": str(by_date_path),
            "by_trade_csv": str(by_trade_path),
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    row = summary.iloc[0]
    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] summary: {summary_path}")
    print(f"[ok] by_date: {by_date_path}")
    print(f"[ok] by_trade: {by_trade_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(
        "Metrics: "
        f"net_total_return={float(row['net_total_return']):.6f}, "
        f"net_sharpe={float(row['net_sharpe']):.6f}, "
        f"net_max_drawdown={float(row['net_max_drawdown']):.6f}, "
        f"rebalance_count={int(row['rebalance_count'])}"
    )


if __name__ == "__main__":
    main()
