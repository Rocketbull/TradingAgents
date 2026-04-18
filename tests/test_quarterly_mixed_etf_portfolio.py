from __future__ import annotations

import pandas as pd
import pytest

from research.quarterly_mixed_etf_portfolio import build_quarterly_portfolio, summarize_portfolio


def test_quarterly_portfolio_rebalances_on_quarter_change() -> None:
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-03-28", "2024-03-29", "2024-04-01", "2024-04-02"]),
            "XLK": [100.0, 110.0, 121.0, 121.0],
            "XLE": [100.0, 100.0, 100.0, 110.0],
        }
    )
    by_date, trade_log = build_quarterly_portfolio(prices, "XLK", "XLE", 0.5, 0.5, 0.0)

    assert bool(by_date.loc[0, "rebalance"])
    assert bool(by_date.loc[2, "rebalance"])
    assert len(trade_log) == 2
    # Weight drift after strong XLK move, then quarter reset.
    assert by_date.loc[1, "weight_a_end"] == pytest.approx(0.5238095238)
    assert trade_log.loc[1, "pre_rebalance_weight_a"] == pytest.approx(0.5238095238)


def test_quarterly_portfolio_summary_matches_equity_curve() -> None:
    prices = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "XLK": [100.0, 101.0, 102.0, 103.0],
            "XLE": [100.0, 99.0, 100.0, 101.0],
        }
    )
    by_date, trade_log = build_quarterly_portfolio(prices, "XLK", "XLE", 0.6, 0.4, 0.0)
    summary = summarize_portfolio(
        by_date=by_date,
        trade_log=trade_log,
        symbol_a="XLK",
        symbol_b="XLE",
        weight_a=0.6,
        weight_b=0.4,
        start_date="2024-01-02",
        end_date="2024-01-05",
        transaction_cost_bps=0.0,
    )

    assert summary.iloc[0]["symbol_a"] == "XLK"
    assert summary.iloc[0]["symbol_b"] == "XLE"
    assert float(summary.iloc[0]["net_total_return"]) == pytest.approx(float(by_date["equity_curve_net"].iloc[-1] - 1.0))
    assert int(summary.iloc[0]["rebalance_count"]) == len(trade_log)
