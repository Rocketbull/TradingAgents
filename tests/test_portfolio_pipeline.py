from __future__ import annotations

import math

import pandas as pd

from tradingagents.alpha import AlphaModel
from tradingagents.alpha.profiles import (
    apply_alpha_profile,
    get_alpha_profile,
    list_alpha_profiles,
)
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
    model = AlphaModel()
    comps = model.component_scores(closes)
    alpha = model.score(closes)
    cov = RiskModel().covariance(closes)
    assert set(alpha.index) == {"AAA", "BBB", "CCC", "SPY"}
    assert set(comps.columns) >= {"mom_1m", "mom_3m", "mom_6m", "rev_1w", "low_vol"}
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


def test_optimizer_returns_details():
    closes = _price_frame()
    alpha = AlphaModel().score(closes)
    cov = RiskModel().covariance(closes)
    optimizer = PortfolioOptimizer(max_weight=0.40, turnover_limit=0.10)
    current = {symbol: 0.25 for symbol in alpha.index}
    target, details = optimizer.optimize(
        alpha,
        cov,
        current_weights=current,
        benchmark_weights={"SPY": 1.0},
        return_details=True,
    )
    assert isinstance(target, dict)
    assert "raw_target_weights" in details
    assert "target_weights" in details
    assert set(details["target_weights"]) == set(target)


def test_ic_weighted_alpha_uses_history():
    closes = _price_frame()
    model = AlphaModel()
    components = model.component_scores(closes, signals=["mom_1m", "rev_1w"])
    # Prefer momentum signal with positive IC and downweight reversal with negative IC.
    ic_history = {
        "mom_1m": [0.12, 0.10, 0.08],
        "rev_1w": [-0.05, -0.02, -0.01],
    }
    combo, weights = model.ic_weighted_alpha(
        components,
        ic_history=ic_history,
        ic_lookback=3,
        weighting_mode="positive",
    )
    assert set(combo.index) == set(components.index)
    assert weights["mom_1m"] > weights["rev_1w"]


def test_ic_weighting_penalizes_highly_correlated_components():
    model = AlphaModel()
    components = pd.DataFrame(
        {
            "alpha_a": [-2.0, -1.0, 0.0, 1.0, 2.0],
            "alpha_b": [-2.0, -1.0, 0.0, 1.0, 2.0],  # perfectly correlated with alpha_a
            "alpha_c": [-2.0, 0.0, 2.0, 0.0, -2.0],  # lower average correlation
        },
        index=["A", "B", "C", "D", "E"],
    )
    ic_history = {"alpha_a": [0.1], "alpha_b": [0.1], "alpha_c": [0.1]}
    _, weights = model.ic_weighted_alpha(
        components=components,
        ic_history=ic_history,
        ic_lookback=1,
        weighting_mode="positive",
        corr_penalty=0.9,
    )
    assert weights["alpha_c"] > weights["alpha_a"]
    assert weights["alpha_c"] > weights["alpha_b"]


def test_alpha_model_from_config_builds_custom_registry():
    closes = _price_frame()
    config = {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_2m", "window": 42},
            {"type": "reversal", "name": "rev_1w", "window": 5},
            {"type": "low_vol", "name": "lv_2m", "window": 42, "enabled": True},
            {"type": "breakout", "name": "bo_6m", "window": 126, "enabled": False},
        ]
    }
    model = AlphaModel.from_config(config)
    assert model.available_signals() == ["mom_2m", "rev_1w", "lv_2m"]
    components = model.component_scores(closes)
    assert set(components.columns) == {"mom_2m", "rev_1w", "lv_2m"}


def test_alpha_profiles_apply_and_list():
    names = list_alpha_profiles()
    assert "conservative" in names

    profile = get_alpha_profile("momentum_heavy")
    assert "alpha_signal_registry" in profile
    assert "alpha_signals" in profile
    assert len(profile["alpha_signal_registry"]) > 0

    cfg = {"foo": "bar"}
    merged = apply_alpha_profile(cfg, "conservative")
    assert merged["foo"] == "bar"
    assert "alpha_signal_registry" in merged
    assert "alpha_signals" in merged


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
