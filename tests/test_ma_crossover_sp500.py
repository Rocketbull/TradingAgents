from __future__ import annotations

import pandas as pd
import pytest

from research.ma_crossover_sp500 import build_ma_crossover_portfolio, summarize_ma_crossover


def test_ma_crossover_uses_next_day_close_to_close_exposure() -> None:
    close = pd.DataFrame(
        {
            "AAA": [10, 10, 10, 10, 10, 12, 14, 16, 18, 20, 18, 16],
            "BBB": [20, 20, 20, 20, 20, 18, 16, 14, 12, 10, 12, 14],
        },
        index=pd.date_range("2024-01-01", periods=12, freq="B"),
        dtype=float,
    )

    daily, signals = build_ma_crossover_portfolio(
        close=close,
        fast_window=2,
        slow_window=4,
        transaction_cost_bps=0.0,
    )

    first_buy_idx = int(daily.index[daily["buy_signals"] > 0][0])
    first_buy_date = pd.Timestamp(daily.loc[first_buy_idx, "date"])
    next_row = daily.loc[first_buy_idx + 1]

    assert int(daily.loc[first_buy_idx, "active_names"]) == 1
    assert pd.Timestamp(next_row["date"]) == first_buy_date + pd.offsets.BDay(1)
    expected_return = close.loc[pd.Timestamp(next_row["date"]), "AAA"] / close.loc[first_buy_date, "AAA"] - 1.0
    assert float(next_row["gross_return"]) == pytest.approx(expected_return)
    assert signals.set_index("symbol").loc["AAA", "buy_signal_count"] >= 1


def test_ma_crossover_summary_includes_benchmark_metrics() -> None:
    close = pd.DataFrame(
        {"AAA": [10, 10, 10, 10, 10, 12, 14, 16, 18, 20, 18, 16]},
        index=pd.date_range("2024-01-01", periods=12, freq="B"),
        dtype=float,
    )
    daily, signals = build_ma_crossover_portfolio(
        close=close,
        fast_window=2,
        slow_window=4,
        transaction_cost_bps=0.0,
    )
    benchmark = pd.Series(
        [100 + i for i in range(12)],
        index=close.index,
        dtype=float,
        name="SPY",
    )

    summary = summarize_ma_crossover(
        daily=daily,
        signal_by_symbol=signals,
        benchmark_close=benchmark,
        start_date="2024-01-01",
        end_date="2024-01-16",
        fast_window=2,
        slow_window=4,
        transaction_cost_bps=0.0,
    )

    row = summary.iloc[0]
    assert row["symbols_with_prices"] == 1
    assert row["benchmark_total_return"] > 0
    assert row["total_return"] == pytest.approx(float(daily["nav"].iloc[-1] - 1.0))


def test_ma_crossover_uses_warmup_history_but_reports_eval_window_only() -> None:
    close = pd.DataFrame(
        {
            "AAA": [10, 10, 10, 12, 14, 16],
            "BBB": [20, 20, 20, 20, 20, 20],
        },
        index=pd.date_range("2024-01-01", periods=6, freq="B"),
        dtype=float,
    )

    daily, signals = build_ma_crossover_portfolio(
        close=close,
        fast_window=2,
        slow_window=4,
        transaction_cost_bps=0.0,
        evaluation_start="2024-01-04",
        evaluation_end="2024-01-08",
    )

    assert list(pd.to_datetime(daily["date"])) == list(pd.date_range("2024-01-04", periods=3, freq="B"))
    assert int(daily.iloc[0]["buy_signals"]) == 1
    assert int(signals.set_index("symbol").loc["AAA", "buy_signal_count"]) == 1
    assert int(signals.set_index("symbol").loc["AAA", "days_with_price"]) == 3
