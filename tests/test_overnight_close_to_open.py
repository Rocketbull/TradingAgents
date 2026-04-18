from __future__ import annotations

import pandas as pd
import pytest

from research.overnight_close_to_open import build_overnight_trades, summarize_overnight_trades


def test_build_overnight_trades_adjusted_prices_and_costs() -> None:
    history = pd.DataFrame(
        {
            "Date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "Open": [99.0, 101.0, 106.0],
            "Close": [100.0, 104.0, 108.0],
            "Adj Close": [50.0, 52.0, 54.0],
        }
    )

    trades = build_overnight_trades(history, price_mode="adjusted", transaction_cost_bps=5.0)

    assert len(trades) == 2
    assert trades.loc[0, "trade_date"] == pd.Timestamp("2024-01-02")
    assert trades.loc[0, "exit_date"] == pd.Timestamp("2024-01-03")
    assert trades.loc[0, "entry_price"] == 50.0
    assert trades.loc[0, "exit_price"] == 50.5
    assert trades.loc[0, "gross_return"] == pytest.approx(0.01)
    assert trades.loc[0, "net_return"] == pytest.approx(0.009)
    assert trades.loc[0, "next_day_intraday_return"] == pytest.approx((52.0 / 50.5) - 1.0)
    assert trades.loc[0, "holding_calendar_days"] == 1


def test_summarize_overnight_trades_returns_expected_trade_count() -> None:
    history = pd.DataFrame(
        {
            "Date": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "Open": [100.0, 101.0, 102.0, 103.0],
            "Close": [100.0, 102.0, 101.0, 104.0],
            "Adj Close": [100.0, 102.0, 101.0, 104.0],
        }
    )

    trades = build_overnight_trades(history, price_mode="raw", transaction_cost_bps=0.0)
    summary = summarize_overnight_trades(
        trades=trades,
        symbol="SPY",
        start_date="2024-01-02",
        end_date="2024-01-05",
        price_mode="raw",
        transaction_cost_bps=0.0,
    )

    assert int(summary.iloc[0]["trade_count"]) == 3
    assert summary.iloc[0]["symbol"] == "SPY"
    assert float(summary.iloc[0]["gross_total_return"]) == float(trades["equity_curve_gross"].iloc[-1] - 1.0)
