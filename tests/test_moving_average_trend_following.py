from __future__ import annotations

import pandas as pd
import pytest

from research.moving_average_trend_following import build_ma_strategy, summarize_ma_strategy


def test_ma_strategy_uses_next_open_execution_without_lookahead() -> None:
    history = pd.DataFrame(
        {
            "Date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "Open": [100.0, 100.0, 101.0, 110.0, 108.0],
            "Close": [100.0, 102.0, 103.0, 98.0, 97.0],
            "Adj Close": [100.0, 102.0, 103.0, 98.0, 97.0],
        }
    )

    by_date, trades = build_ma_strategy(history, ma_window=2, price_mode="adjusted", transaction_cost_bps=0.0)

    # Day 2024-01-02 closes above its 2-day MA, but the long starts at the next open on 2024-01-03.
    row_0102 = by_date.loc[by_date["date"] == pd.Timestamp("2024-01-02")].iloc[0]
    row_0103 = by_date.loc[by_date["date"] == pd.Timestamp("2024-01-03")].iloc[0]
    assert int(row_0102["position_open"]) == 0
    assert bool(row_0102["cross_above"])
    assert int(row_0103["position_open"]) == 1
    assert row_0103["strategy_gross_return"] == pytest.approx((110.0 / 101.0) - 1.0)

    assert list(trades["action"]) == ["BUY", "SELL"]
    assert list(trades["trade_date"]) == [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")]


def test_ma_strategy_summary_contains_basic_metrics() -> None:
    history = pd.DataFrame(
        {
            "Date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"],
            "Open": [100.0, 100.0, 101.0, 110.0, 108.0, 95.0],
            "Close": [100.0, 102.0, 103.0, 98.0, 97.0, 96.0],
            "Adj Close": [100.0, 102.0, 103.0, 98.0, 97.0, 96.0],
        }
    )

    by_date, trades = build_ma_strategy(history, ma_window=2)
    summary = summarize_ma_strategy(
        by_date=by_date,
        trades=trades,
        symbol="SPY",
        start_date="2024-01-01",
        end_date="2024-01-08",
        ma_window=2,
        price_mode="adjusted",
        transaction_cost_bps=0.0,
    )

    assert summary.iloc[0]["symbol"] == "SPY"
    assert int(summary.iloc[0]["trade_count"]) == 2
    assert int(summary.iloc[0]["entry_count"]) == 1
    assert int(summary.iloc[0]["exit_count"]) == 1
    assert float(summary.iloc[0]["net_total_return"]) == pytest.approx(float(by_date["equity_curve_net"].iloc[-1] - 1.0))
