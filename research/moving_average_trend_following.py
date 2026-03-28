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
        description="Research strategy: buy when price closes above moving average, sell when it closes below."
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
        "--ma-window",
        type=int,
        default=100,
        help="Moving average window in trading days.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=0.0,
        help="Per-side transaction cost in basis points.",
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


def _prepare_prices(history: pd.DataFrame, price_mode: str) -> pd.DataFrame:
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
        adjustment_factor = (df["Adj Close"] / df["Close"]).replace([np.inf, -np.inf], np.nan)
        df["price_close"] = df["Adj Close"]
        df["price_open"] = df["Open"] * adjustment_factor
    else:
        df["price_close"] = df["Close"]
        df["price_open"] = df["Open"]

    return df


def build_ma_strategy(
    history: pd.DataFrame,
    ma_window: int = 100,
    price_mode: str = "adjusted",
    transaction_cost_bps: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if ma_window < 2:
        raise ValueError("ma_window must be >= 2")

    df = _prepare_prices(history, price_mode=price_mode)
    df["ma"] = df["price_close"].rolling(ma_window, min_periods=ma_window).mean()
    df["signal_above_ma"] = df["price_close"] > df["ma"]
    prev_signal = df["signal_above_ma"].shift(1, fill_value=False)
    df["cross_above"] = df["signal_above_ma"] & ~prev_signal
    df["cross_below"] = ~df["signal_above_ma"] & prev_signal

    # Signal is observed at the close; position changes at the next session open.
    df["position_open"] = df["signal_above_ma"].shift(1, fill_value=False).astype(int)
    df["next_open_price"] = df["price_open"].shift(-1)
    df["buy_hold_open_to_open_return"] = df["next_open_price"] / df["price_open"] - 1.0
    df["strategy_gross_return"] = df["position_open"] * df["buy_hold_open_to_open_return"]

    df["turnover"] = df["position_open"].diff().abs().fillna(df["position_open"])
    per_side_cost = float(transaction_cost_bps) / 10000.0
    df["cost"] = df["turnover"] * per_side_cost
    df["strategy_net_return"] = df["strategy_gross_return"] - df["cost"]

    valid = df[(df["ma"].notna()) & (df["next_open_price"].notna())].copy()
    if valid.empty:
        raise ValueError("No valid rows available after moving-average warmup and next-open alignment.")

    valid["equity_curve_gross"] = (1.0 + valid["strategy_gross_return"]).cumprod()
    valid["equity_curve_net"] = (1.0 + valid["strategy_net_return"]).cumprod()
    valid["buy_hold_equity_curve"] = (1.0 + valid["buy_hold_open_to_open_return"]).cumprod()
    valid["drawdown_net"] = valid["equity_curve_net"] / valid["equity_curve_net"].cummax() - 1.0

    by_date = valid[
        [
            "Date",
            "price_open",
            "next_open_price",
            "price_close",
            "ma",
            "signal_above_ma",
            "cross_above",
            "cross_below",
            "position_open",
            "buy_hold_open_to_open_return",
            "strategy_gross_return",
            "strategy_net_return",
            "turnover",
            "cost",
            "equity_curve_gross",
            "equity_curve_net",
            "buy_hold_equity_curve",
            "drawdown_net",
        ]
    ].copy()
    by_date = by_date.rename(
        columns={
            "Date": "date",
            "price_open": "open_price",
            "next_open_price": "next_open_price",
            "price_close": "close_price",
        }
    ).reset_index(drop=True)

    trade_rows: list[dict[str, Any]] = []
    for idx in range(1, len(df)):
        trade_date = df.loc[idx, "Date"]
        signal_date = df.loc[idx - 1, "Date"]
        action = None
        reason = None
        if bool(df.loc[idx - 1, "cross_above"]):
            action = "BUY"
            reason = "close_cross_above_ma"
        elif bool(df.loc[idx - 1, "cross_below"]):
            action = "SELL"
            reason = "close_cross_below_ma"
        if action is None:
            continue
        if pd.isna(df.loc[idx, "price_open"]):
            continue
        trade_rows.append(
            {
                "signal_date": signal_date,
                "trade_date": trade_date,
                "action": action,
                "reason": reason,
                "trade_price": float(df.loc[idx, "price_open"]),
                "signal_close_price": float(df.loc[idx - 1, "price_close"]),
                "signal_ma": float(df.loc[idx - 1, "ma"]) if pd.notna(df.loc[idx - 1, "ma"]) else float("nan"),
            }
        )
    trades = pd.DataFrame(trade_rows)

    return by_date, trades


def summarize_ma_strategy(
    by_date: pd.DataFrame,
    trades: pd.DataFrame,
    symbol: str,
    start_date: str,
    end_date: str,
    ma_window: int,
    price_mode: str,
    transaction_cost_bps: float,
) -> pd.DataFrame:
    invested = by_date[by_date["position_open"] > 0].copy()
    buys = int((trades["action"] == "BUY").sum()) if not trades.empty else 0
    sells = int((trades["action"] == "SELL").sum()) if not trades.empty else 0

    net_total_return = float(by_date["equity_curve_net"].iloc[-1] - 1.0)
    gross_total_return = float(by_date["equity_curve_gross"].iloc[-1] - 1.0)
    buy_hold_return = float(by_date["buy_hold_equity_curve"].iloc[-1] - 1.0)

    summary = pd.DataFrame(
        [
            {
                "symbol": str(symbol).upper(),
                "start_date": start_date,
                "end_date": end_date,
                "ma_window": int(ma_window),
                "price_mode": price_mode,
                "transaction_cost_bps_per_side": float(transaction_cost_bps),
                "trade_count": int(trades.shape[0]),
                "entry_count": buys,
                "exit_count": sells,
                "days_tested": int(by_date.shape[0]),
                "days_in_market": int(by_date["position_open"].sum()),
                "days_in_market_ratio": float(by_date["position_open"].mean()),
                "gross_total_return": gross_total_return,
                "net_total_return": net_total_return,
                "net_annualized_return": _annualized_return(net_total_return, int(by_date.shape[0])),
                "net_annualized_volatility": _annualized_volatility(by_date["strategy_net_return"]),
                "net_sharpe": _sharpe_ratio(by_date["strategy_net_return"]),
                "net_max_drawdown": _max_drawdown(by_date["equity_curve_net"]),
                "buy_and_hold_return_same_window": buy_hold_return,
                "mean_gross_return": float(by_date["strategy_gross_return"].mean()),
                "median_gross_return": float(by_date["strategy_gross_return"].median()),
                "mean_net_return": float(by_date["strategy_net_return"].mean()),
                "median_net_return": float(by_date["strategy_net_return"].median()),
                "net_win_rate": float((invested["strategy_net_return"] > 0.0).mean()) if not invested.empty else float("nan"),
                "avg_win_return": float(invested.loc[invested["strategy_net_return"] > 0.0, "strategy_net_return"].mean())
                if not invested.empty and (invested["strategy_net_return"] > 0.0).any()
                else float("nan"),
                "avg_loss_return": float(invested.loc[invested["strategy_net_return"] < 0.0, "strategy_net_return"].mean())
                if not invested.empty and (invested["strategy_net_return"] < 0.0).any()
                else float("nan"),
                "buy_signal_count": int(by_date["cross_above"].sum()),
                "sell_signal_count": int(by_date["cross_below"].sum()),
            }
        ]
    )
    return summary


def main() -> None:
    args = parse_args()
    params: dict[str, Any] = {
        "script": "moving_average_trend_following",
        "symbol": str(args.symbol).upper(),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "ma_window": int(args.ma_window),
        "price_mode": args.price_mode,
        "transaction_cost_bps_per_side": float(args.transaction_cost_bps),
    }
    run_manager = ResearchRunManager(
        out_dir=Path(args.output_dir),
        params=params,
        run_tag=args.run_tag,
        tag_prefix="ma_trend",
    )
    run_dir = run_manager.run_dir()

    history = load_history_window(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        root_dir=args.data_dir,
    )
    by_date, trades = build_ma_strategy(
        history=history,
        ma_window=args.ma_window,
        price_mode=args.price_mode,
        transaction_cost_bps=args.transaction_cost_bps,
    )
    summary = summarize_ma_strategy(
        by_date=by_date,
        trades=trades,
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        ma_window=args.ma_window,
        price_mode=args.price_mode,
        transaction_cost_bps=args.transaction_cost_bps,
    )

    summary_path = run_dir / "summary.csv"
    by_date_path = run_dir / "by_date.csv"
    by_trade_path = run_dir / "by_trade.csv"
    summary.to_csv(summary_path, index=False)
    by_date.to_csv(by_date_path, index=False)
    trades.to_csv(by_trade_path, index=False)

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
        f"trade_count={int(row['trade_count'])}, "
        f"net_total_return={float(row['net_total_return']):.6f}, "
        f"net_sharpe={float(row['net_sharpe']):.6f}, "
        f"net_max_drawdown={float(row['net_max_drawdown']):.6f}, "
        f"days_in_market_ratio={float(row['days_in_market_ratio']):.6f}"
    )


if __name__ == "__main__":
    main()
