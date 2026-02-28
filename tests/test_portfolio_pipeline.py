from __future__ import annotations

import math

import pandas as pd

from tradingagents.portfolio.alpha_model import AlphaModel
from tradingagents.portfolio.optimizer import PortfolioOptimizer
from tradingagents.portfolio.rebalance import Rebalancer
from tradingagents.portfolio.risk_model import RiskModel


def _price_frame() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    return pd.DataFrame(
        {
            "AAA": pd.Series(range(100, 400), index=idx, dtype=float),
            "BBB": pd.Series(range(200, 500), index=idx, dtype=float),
            "CCC": pd.Series(range(300, 600), index=idx, dtype=float),
            "SPY": pd.Series(range(250, 550), index=idx, dtype=float),
        }
    )


def test_alpha_and_risk_model_shapes():
    closes = _price_frame()
    alpha = AlphaModel().score(closes)
    cov = RiskModel().covariance(closes)
    assert set(alpha.index) == {"AAA", "BBB", "CCC", "SPY"}
    assert cov.shape == (4, 4)
    assert list(cov.index) == list(cov.columns)


def test_optimizer_constraints_and_turnover():
    closes = _price_frame()
    alpha = AlphaModel().score(closes)
    cov = RiskModel().covariance(closes)
    optimizer = PortfolioOptimizer(max_weight=0.40, turnover_limit=0.10)
    current = {symbol: 0.25 for symbol in alpha.index}
    target = optimizer.optimize(alpha, cov, current_weights=current, benchmark_weights={"SPY": 1.0})

    assert math.isclose(sum(target.values()), 1.0, rel_tol=1e-6)
    assert all(0.0 <= weight <= 0.40 + 1e-9 for weight in target.values())
    turnover = sum(abs(target[s] - current.get(s, 0.0)) for s in target)
    assert turnover <= 0.10 + 1e-6


def test_rebalancer_generates_orders():
    reb = Rebalancer(transaction_cost_bps=10.0)
    current = {"AAA": 0.5, "BBB": 0.5}
    target = {"AAA": 0.3, "BBB": 0.7}
    orders = reb.generate_orders(current_weights=current, target_weights=target, portfolio_value=1_000_000)

    assert len(orders) == 2
    by_symbol = {row["symbol"]: row for row in orders}
    assert by_symbol["AAA"]["action"] == "SELL"
    assert by_symbol["BBB"]["action"] == "BUY"
    assert by_symbol["AAA"]["estimated_cost"] > 0
    assert by_symbol["BBB"]["estimated_cost"] > 0

