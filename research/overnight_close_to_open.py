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
from activeportfolio.dataflows.market_data_store import load_history_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Research strategy: buy at close and sell next trading session open."
    )
    parser.add_argument("--symbol", default="SPY", help="Ticker symbol to study.")
    parser.add_argument("--data-dir", default="data/market", help="Parquet root directory.")
    parser.add_argument("--output-dir", default="research/output", help="Research output directory.")
    parser.add_argument("--run-tag", default=None, help="Optional run tag.")
    parser.add_argument(
        "--config-json",
        default=None,
        help="Optional config JSON path recorded in the run manifest.",
    )
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD.")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD.")
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=0.0,
        help="Per-side transaction cost in basis points. Round trip cost is 2x this value.",
    )
    parser.add_argument(
        "--price-mode",
        default="adjusted",
        choices=["adjusted", "raw"],
        help="Use split/dividend-adjusted prices when available, or raw OHLC prices.",
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


def build_overnight_trades(
    history: pd.DataFrame,
    price_mode: str = "adjusted",
    transaction_cost_bps: float = 0.0,
) -> pd.DataFrame:
    required_columns = {"Date", "Open", "Close"}
    missing = required_columns - set(history.columns)
    if missing:
        raise ValueError(f"History is missing required columns: {sorted(missing)}")

    use_adjusted = price_mode == "adjusted" and "Adj Close" in history.columns
    df = history.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    for column in ["Open", "Close"] + (["Adj Close"] if "Adj Close" in df.columns else []):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if use_adjusted:
        adjustment_factor = df["Adj Close"] / df["Close"]
        adjustment_factor = adjustment_factor.replace([np.inf, -np.inf], np.nan)
        df["entry_price"] = df["Adj Close"]
        df["exit_price"] = df["Open"].shift(-1) * adjustment_factor.shift(-1)
        df["next_close_price"] = df["Adj Close"].shift(-1)
    else:
        df["entry_price"] = df["Close"]
        df["exit_price"] = df["Open"].shift(-1)
        df["next_close_price"] = df["Close"].shift(-1)

    df["exit_date"] = df["Date"].shift(-1)
    df["next_raw_open"] = df["Open"].shift(-1)
    df["gross_return"] = df["exit_price"] / df["entry_price"] - 1.0
    df["next_day_intraday_return"] = df["next_close_price"] / df["exit_price"] - 1.0

    round_trip_cost = 2.0 * float(transaction_cost_bps) / 10000.0
    df["net_return"] = df["gross_return"] - round_trip_cost

    trades = df.dropna(
        subset=["Date", "exit_date", "entry_price", "exit_price", "gross_return", "net_return"]
    ).copy()
    if trades.empty:
        raise ValueError("No valid overnight trades could be constructed from the history window.")

    trades = trades.rename(
        columns={
            "Date": "trade_date",
            "Close": "raw_close",
            "Open": "raw_open",
        }
    )
    trades["holding_calendar_days"] = (
        pd.to_datetime(trades["exit_date"]) - pd.to_datetime(trades["trade_date"])
    ).dt.days
    trades["equity_curve_gross"] = (1.0 + trades["gross_return"]).cumprod()
    trades["equity_curve_net"] = (1.0 + trades["net_return"]).cumprod()
    trades["drawdown_net"] = trades["equity_curve_net"] / trades["equity_curve_net"].cummax() - 1.0

    ordered_cols = [
        "trade_date",
        "exit_date",
        "raw_close",
        "next_raw_open",
        "entry_price",
        "exit_price",
        "next_close_price",
        "gross_return",
        "net_return",
        "next_day_intraday_return",
        "holding_calendar_days",
        "equity_curve_gross",
        "equity_curve_net",
        "drawdown_net",
    ]
    return trades[ordered_cols].reset_index(drop=True)


def summarize_overnight_trades(
    trades: pd.DataFrame,
    symbol: str,
    start_date: str,
    end_date: str,
    price_mode: str,
    transaction_cost_bps: float,
) -> pd.DataFrame:
    gross_total_return = float(trades["equity_curve_gross"].iloc[-1] - 1.0)
    net_total_return = float(trades["equity_curve_net"].iloc[-1] - 1.0)

    win_mask = trades["net_return"] > 0.0
    loss_mask = trades["net_return"] < 0.0
    buy_and_hold_return = float(trades["next_close_price"].iloc[-1] / trades["entry_price"].iloc[0] - 1.0)
    open_to_close_total_return = float((1.0 + trades["next_day_intraday_return"]).prod() - 1.0)

    summary = pd.DataFrame(
        [
            {
                "symbol": str(symbol).upper(),
                "start_date": start_date,
                "end_date": end_date,
                "price_mode": price_mode,
                "transaction_cost_bps_per_side": float(transaction_cost_bps),
                "trade_count": int(trades.shape[0]),
                "first_trade_date": pd.Timestamp(trades["trade_date"].iloc[0]).strftime("%Y-%m-%d"),
                "last_exit_date": pd.Timestamp(trades["exit_date"].iloc[-1]).strftime("%Y-%m-%d"),
                "gross_total_return": gross_total_return,
                "net_total_return": net_total_return,
                "net_annualized_return": _annualized_return(net_total_return, int(trades.shape[0])),
                "net_annualized_volatility": _annualized_volatility(trades["net_return"]),
                "net_sharpe": _sharpe_ratio(trades["net_return"]),
                "net_max_drawdown": _max_drawdown(trades["equity_curve_net"]),
                "net_win_rate": float(win_mask.mean()),
                "mean_gross_return": float(trades["gross_return"].mean()),
                "median_gross_return": float(trades["gross_return"].median()),
                "mean_net_return": float(trades["net_return"].mean()),
                "median_net_return": float(trades["net_return"].median()),
                "avg_win_return": float(trades.loc[win_mask, "net_return"].mean()) if win_mask.any() else float("nan"),
                "avg_loss_return": float(trades.loc[loss_mask, "net_return"].mean()) if loss_mask.any() else float("nan"),
                "mean_holding_calendar_days": float(trades["holding_calendar_days"].mean()),
                "buy_and_hold_return_same_window": buy_and_hold_return,
                "open_to_close_total_return_same_days": open_to_close_total_return,
                "mean_next_day_intraday_return": float(trades["next_day_intraday_return"].mean()),
                "overnight_minus_intraday_mean_return": float(
                    trades["gross_return"].mean() - trades["next_day_intraday_return"].mean()
                ),
            }
        ]
    )
    return summary


def main() -> None:
    args = parse_args()
    params: dict[str, Any] = {
        "script": "overnight_close_to_open",
        "symbol": str(args.symbol).upper(),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "price_mode": args.price_mode,
        "transaction_cost_bps_per_side": float(args.transaction_cost_bps),
    }
    run_manager = ResearchRunManager(
        out_dir=Path(args.output_dir),
        params=params,
        run_tag=args.run_tag,
        tag_prefix="overnight",
    )
    run_dir = run_manager.run_dir()

    history = load_history_window(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        root_dir=args.data_dir,
    )
    trades = build_overnight_trades(
        history=history,
        price_mode=args.price_mode,
        transaction_cost_bps=args.transaction_cost_bps,
    )
    summary = summarize_overnight_trades(
        trades=trades,
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        price_mode=args.price_mode,
        transaction_cost_bps=args.transaction_cost_bps,
    )

    by_trade_path = run_dir / "by_trade.csv"
    summary_path = run_dir / "summary.csv"
    trades.to_csv(by_trade_path, index=False)
    summary.to_csv(summary_path, index=False)

    params_path = run_manager.write_params(
        extra={
            "trade_count": int(summary.iloc[0]["trade_count"]),
            "net_total_return": float(summary.iloc[0]["net_total_return"]),
            "net_sharpe": float(summary.iloc[0]["net_sharpe"]),
        }
    )
    manifest_path = run_manager.write_manifest(
        artifacts={
            "summary_csv": str(summary_path),
            "by_trade_csv": str(by_trade_path),
            "params_json": str(params_path),
        },
        config_json=args.config_json,
    )

    row = summary.iloc[0]
    print(f"[ok] run_tag: {run_manager.resolved_run_tag()}")
    print(f"[ok] by_trade: {by_trade_path}")
    print(f"[ok] summary: {summary_path}")
    print(f"[ok] params: {params_path}")
    print(f"[ok] manifest: {manifest_path}")
    print(
        "Metrics: "
        f"trade_count={int(row['trade_count'])}, "
        f"net_total_return={float(row['net_total_return']):.6f}, "
        f"net_sharpe={float(row['net_sharpe']):.6f}, "
        f"net_max_drawdown={float(row['net_max_drawdown']):.6f}, "
        f"net_win_rate={float(row['net_win_rate']):.6f}"
    )


if __name__ == "__main__":
    main()
