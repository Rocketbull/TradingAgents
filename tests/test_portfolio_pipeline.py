from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from tradingagents.alpha import AlphaModel
from tradingagents.alpha.signals import FlatVolumeBreakoutAlpha
from tradingagents.alpha.profiles import (
    apply_alpha_profile,
    get_alpha_profile,
    list_alpha_profiles,
)
from tradingagents.portfolio.optimizer import PortfolioOptimizer
from tradingagents.portfolio.rebalance import Rebalancer
from tradingagents.portfolio.risk_model import RiskModel
from tradingagents.portfolio.attribution import AttributionEngine


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


def _volume_frame() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    n = len(idx)
    return pd.DataFrame(
        {
            "AAA": pd.Series([1_000_000.0] * n, index=idx, dtype=float),
            "BBB": pd.Series([800_000.0] * n, index=idx, dtype=float),
            "CCC": pd.Series([600_000.0] * n, index=idx, dtype=float),
            "SPY": pd.Series([2_000_000.0] * n, index=idx, dtype=float),
        }
    )


def _breakout_close_volume_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    aaa = [100.0] * 90 + list(pd.Series(range(100, 130), dtype=float))
    bbb = [100.0] * 120
    ccc = [100.0] * 120
    closes = pd.DataFrame(
        {
            "AAA": pd.Series(aaa, index=idx, dtype=float),
            "BBB": pd.Series(bbb, index=idx, dtype=float),
            "CCC": pd.Series(ccc, index=idx, dtype=float),
        }
    )
    vol_aaa = [1_000_000.0] * 115 + [2_500_000.0] * 5
    volumes = pd.DataFrame(
        {
            "AAA": pd.Series(vol_aaa, index=idx, dtype=float),
            "BBB": pd.Series([800_000.0] * 120, index=idx, dtype=float),
            "CCC": pd.Series([700_000.0] * 120, index=idx, dtype=float),
        }
    )
    return closes, volumes


def _breakout_strength_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    strong = [100.0] * 90 + list(pd.Series(range(100, 130), dtype=float))
    weak = [100.0] * 95 + list(pd.Series(range(100, 125), dtype=float))
    closes = pd.DataFrame(
        {
            "STRONG": pd.Series(strong, index=idx, dtype=float),
            "WEAK": pd.Series(weak, index=idx, dtype=float),
        }
    )
    vol_strong = [1_000_000.0] * 115 + [3_000_000.0] * 5
    vol_weak = [1_000_000.0] * 115 + [1_900_000.0] * 5
    volumes = pd.DataFrame(
        {
            "STRONG": pd.Series(vol_strong, index=idx, dtype=float),
            "WEAK": pd.Series(vol_weak, index=idx, dtype=float),
        }
    )
    return closes, volumes


def _btc_gld_corr_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=220, freq="D")
    t = pd.Series(range(len(idx)), index=idx, dtype=float)
    btc = 100.0 + 0.30 * t
    gld = 200.0 + 0.05 * t
    aaa = 50.0 + 0.28 * t   # BTC-like
    bbb = 80.0 + 0.06 * t   # GLD-like
    ccc = 60.0 + 0.17 * t   # mixed
    return pd.DataFrame(
        {
            "AAA": aaa,
            "BBB": bbb,
            "CCC": ccc,
            "BTC-USD": btc,
            "GLD": gld,
        },
        index=idx,
    )


def _volume_shock_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range("2025-01-01", periods=90, freq="D")
    aaa_close = [100.0] * 70 + list(pd.Series(range(100, 120), dtype=float))
    bbb_close = [100.0] * 90
    ccc_close = [100.0] * 80 + list(pd.Series(range(100, 110), dtype=float))
    closes = pd.DataFrame(
        {
            "AAA": pd.Series(aaa_close, index=idx, dtype=float),
            "BBB": pd.Series(bbb_close, index=idx, dtype=float),
            "CCC": pd.Series(ccc_close, index=idx, dtype=float),
        }
    )
    aaa_vol = [1_000_000.0] * 85 + [2_500_000.0] * 5
    bbb_vol = [1_000_000.0] * 90
    ccc_vol = [1_000_000.0] * 85 + [1_200_000.0] * 5
    volumes = pd.DataFrame(
        {
            "AAA": pd.Series(aaa_vol, index=idx, dtype=float),
            "BBB": pd.Series(bbb_vol, index=idx, dtype=float),
            "CCC": pd.Series(ccc_vol, index=idx, dtype=float),
        }
    )
    return closes, volumes


def _sector_momentum_frame() -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=90, freq="D")
    t = pd.Series(range(len(idx)), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "AAA": 100.0 + 1.20 * t,
            "BBB": 100.0 + 0.30 * t,
            "CCC": 100.0 + 0.90 * t,
            "DDD": 100.0 + 0.10 * t,
        },
        index=idx,
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


def test_optimizer_enforces_sector_cap():
    closes = _price_frame()
    alpha = AlphaModel().score(closes)
    cov = RiskModel().covariance(closes)
    optimizer = PortfolioOptimizer(max_weight=0.8, turnover_limit=1.0, sector_cap=0.6)
    current = {symbol: 0.25 for symbol in alpha.index}
    sectors = {
        "AAA": "Tech",
        "BBB": "Tech",
        "CCC": "Utilities",
        "SPY": "Utilities",
    }
    target = optimizer.optimize(
        alpha,
        cov,
        current_weights=current,
        benchmark_weights={"SPY": 1.0},
        sector_map=sectors,
    )
    sector_totals = {}
    for symbol, weight in target.items():
        sector = sectors[symbol]
        sector_totals[sector] = sector_totals.get(sector, 0.0) + float(weight)
    assert sector_totals["Tech"] <= 0.600001
    assert sector_totals["Utilities"] <= 0.600001


def test_optimizer_enforces_active_weight_cap():
    closes = _price_frame()
    alpha = AlphaModel().score(closes)
    cov = RiskModel().covariance(closes)
    benchmark = {symbol: 0.25 for symbol in alpha.index}
    optimizer = PortfolioOptimizer(
        max_weight=0.60,
        active_weight_cap=0.05,
        turnover_limit=1.0,
    )
    target = optimizer.optimize(
        alpha_scores=alpha,
        covariance=cov,
        current_weights=benchmark,
        benchmark_weights=benchmark,
    )
    for symbol in alpha.index:
        assert abs(float(target[symbol]) - float(benchmark[symbol])) <= 0.050001


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


def test_ic_weight_stabilization_caps_concentration():
    model = AlphaModel()
    components = pd.DataFrame(
        {
            "s1": [-2.0, -1.0, 0.0, 1.0, 2.0],
            "s2": [-1.0, 0.0, 1.0, 0.0, -1.0],
            "s3": [2.0, 1.0, 0.0, -1.0, -2.0],
        },
        index=["A", "B", "C", "D", "E"],
    )
    ic_history = {"s1": [0.9, 0.8], "s2": [0.01, 0.02], "s3": [0.01, 0.02]}
    _, weights = model.ic_weighted_alpha(
        components=components,
        ic_history=ic_history,
        ic_lookback=2,
        weighting_mode="positive",
        max_signal_weight=0.6,
        prev_weights={"s1": 0.2, "s2": 0.4, "s3": 0.4},
        weight_smoothing=0.5,
        ic_ewm_decay=0.9,
    )
    assert max(abs(v) for v in weights.values()) <= 0.600001
    assert abs(sum(abs(v) for v in weights.values()) - 1.0) <= 1e-6


def test_ic_threshold_gate_zeroes_weak_signal():
    model = AlphaModel()
    components = pd.DataFrame(
        {
            "strong": [-2.0, -1.0, 0.0, 1.0, 2.0],
            "weak": [2.0, 1.0, 0.0, -1.0, -2.0],
        },
        index=["A", "B", "C", "D", "E"],
    )
    ic_history = {
        "strong": [0.06, 0.05, 0.04, 0.03],
        "weak": [0.004, 0.003, 0.002, 0.001],
    }
    _, weights = model.ic_weighted_alpha(
        components=components,
        ic_history=ic_history,
        ic_lookback=4,
        weighting_mode="positive",
        ic_gate_min_mean=0.01,
    )
    assert weights["strong"] > 0.99
    assert abs(weights["weak"]) < 1e-8


def test_ic_significance_gate_filters_unstable_signal():
    model = AlphaModel()
    components = pd.DataFrame(
        {
            "stable": [-2.0, -1.0, 0.0, 1.0, 2.0],
            "noisy": [2.0, -1.0, 1.0, -2.0, 0.0],
        },
        index=["A", "B", "C", "D", "E"],
    )
    ic_history = {
        "stable": [0.03, 0.03, 0.03, 0.03, 0.03, 0.03],
        "noisy": [0.2, -0.2, 0.2, -0.2, 0.2, -0.2],
    }
    _, weights = model.ic_weighted_alpha(
        components=components,
        ic_history=ic_history,
        ic_lookback=6,
        weighting_mode="positive",
        ic_gate_min_tstat=1.0,
        ic_gate_min_hit_rate=0.5,
        ic_gate_min_samples=6,
    )
    assert weights["stable"] > 0.99
    assert abs(weights["noisy"]) < 1e-8


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


def test_alpha_model_registry_builds_flat_volume_breakout():
    closes, volumes = _breakout_close_volume_frames()
    config = {
        "alpha_signal_registry": [
            {
                "type": "flat_vol_breakout",
                "name": "flat_vol",
                "flat_window": 60,
                "flat_max_abs_return": 0.15,
                "price_window": 20,
                "price_ratio_min": 1.10,
                "vol_short_window": 5,
                "vol_long_window": 20,
                "vol_ratio_min": 1.50,
            }
        ]
    }
    model = AlphaModel.from_config(config)
    assert model.available_signals() == ["flat_vol"]
    components = model.component_scores(closes, volumes=volumes)
    assert set(components.columns) == {"flat_vol"}


def test_flat_volume_breakout_signal_triggers_for_synthetic_pattern():
    closes, volumes = _breakout_close_volume_frames()
    model = AlphaModel.from_config(
        {
            "alpha_signal_registry": [
                {
                    "type": "flat_vol_breakout",
                    "name": "flat_vol",
                    "flat_window": 60,
                    "flat_max_abs_return": 0.15,
                    "price_window": 20,
                    "price_ratio_min": 1.10,
                    "vol_short_window": 5,
                    "vol_long_window": 20,
                    "vol_ratio_min": 1.50,
                }
            ]
        }
    )
    comps = model.component_scores(closes, volumes=volumes)
    # AAA has flat regime + price breakout + volume surge, others do not.
    assert float(comps.loc["AAA", "flat_vol"]) > 0.0
    assert float(comps.loc["BBB", "flat_vol"]) <= 0.0
    assert float(comps.loc["CCC", "flat_vol"]) <= 0.0


def test_flat_volume_breakout_scores_strength_continuously():
    closes, volumes = _breakout_strength_frames()
    signal = FlatVolumeBreakoutAlpha(
        name="flat_vol",
        flat_window=60,
        flat_max_abs_return=0.15,
        price_window=20,
        price_ratio_min=1.10,
        vol_short_window=5,
        vol_long_window=20,
        vol_ratio_min=1.50,
    )
    raw = signal.compute(closes, volumes=volumes)
    assert float(raw.loc["STRONG"]) > float(raw.loc["WEAK"])
    assert float(raw.loc["WEAK"]) > 0.0


def test_alpha_model_registry_builds_btc_gld_corr_signal():
    closes = _btc_gld_corr_frame()
    model = AlphaModel.from_config(
        {
            "alpha_signal_registry": [
                {
                    "type": "btc_gld_corr",
                    "name": "btc_gld_corr",
                    "lookback_window": 60,
                    "risk_symbol": "BTC-USD",
                    "defensive_symbol": "GLD",
                    "flip_sign": True,
                }
            ]
        }
    )
    comps = model.component_scores(closes)
    assert set(comps.columns) == {"btc_gld_corr"}
    assert float(comps["btc_gld_corr"].abs().sum()) > 0.0


def test_alpha_model_registry_builds_new_signal_types():
    closes, volumes = _volume_shock_frame()
    model = AlphaModel.from_config(
        {
            "alpha_signal_registry": [
                {"type": "vol_adj_momentum", "name": "vam", "momentum_window": 21, "vol_window": 10},
                {"type": "range_position", "name": "range_1m", "window": 21},
                {
                    "type": "volume_shock",
                    "name": "vol_shock",
                    "price_window": 5,
                    "vol_short_window": 5,
                    "vol_long_window": 20,
                },
            ]
        }
    )
    comps = model.component_scores(closes, volumes=volumes)
    assert set(comps.columns) == {"vam", "range_1m", "vol_shock"}
    assert float(comps["vam"].abs().sum()) > 0.0
    assert float(comps["range_1m"].abs().sum()) > 0.0
    assert float(comps["vol_shock"].abs().sum()) > 0.0


def test_alpha_model_registry_builds_sector_momentum_top2(tmp_path: Path):
    closes = _sector_momentum_frame()
    cls_path = tmp_path / "classification.csv"
    cls_path.write_text(
        "symbol,sector\n"
        "AAA,Technology\n"
        "BBB,Technology\n"
        "CCC,Utilities\n"
        "DDD,Utilities\n",
        encoding="utf-8",
    )
    model = AlphaModel.from_config(
        {
            "alpha_signal_registry": [
                {
                    "type": "sector_momentum_top2",
                    "name": "sec_mom_top1",
                    "momentum_window": 21,
                    "top_k_per_sector": 1,
                    "sector_classification_cache": str(cls_path),
                }
            ]
        }
    )
    comps = model.component_scores(closes)
    assert set(comps.columns) == {"sec_mom_top1"}
    # Top-1 per sector should prefer AAA over BBB and CCC over DDD.
    assert float(comps.loc["AAA", "sec_mom_top1"]) > float(comps.loc["BBB", "sec_mom_top1"])
    assert float(comps.loc["CCC", "sec_mom_top1"]) > float(comps.loc["DDD", "sec_mom_top1"])


def test_alpha_profiles_apply_and_list():
    names = list_alpha_profiles()
    assert "conservative" in names
    assert "diversified_sp500_v1" in names

    profile = get_alpha_profile("momentum_heavy")
    assert "alpha_signal_registry" in profile
    assert "alpha_signals" in profile
    assert len(profile["alpha_signal_registry"]) > 0

    cfg = {"foo": "bar"}
    merged = apply_alpha_profile(cfg, "conservative")
    assert merged["foo"] == "bar"
    assert "alpha_signal_registry" in merged
    assert "alpha_signals" in merged


def test_attribution_transfer_coefficient_uses_pre_post_active_weights():
    alpha = pd.Series({"AAA": 1.0, "BBB": 0.5, "CCC": -0.2, "DDD": -1.0})
    realized = pd.Series({"AAA": 0.02, "BBB": 0.01, "CCC": -0.01, "DDD": -0.02})
    unconstrained_active = {"AAA": 0.10, "BBB": 0.03, "CCC": -0.03, "DDD": -0.10}
    constrained_active = {"AAA": 0.06, "BBB": 0.02, "CCC": -0.02, "DDD": -0.06}
    target_weights = {"AAA": 0.31, "BBB": 0.27, "CCC": 0.23, "DDD": 0.19}

    metrics = AttributionEngine().diagnostics(
        alpha_scores=alpha,
        realized_returns=realized,
        target_weights=target_weights,
        unconstrained_active_weights=unconstrained_active,
        constrained_active_weights=constrained_active,
    )
    assert metrics["transfer_coefficient_proxy"] > 0.99


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


def test_risk_model_sector_and_beta_helpers():
    symbols = ["AAA", "BBB", "CCC"]
    sector_map = {"AAA": "Technology", "CCC": "Utilities"}
    beta_map = {"AAA": 1.2, "BBB": 0.8}

    exposure = RiskModel.sector_exposure_matrix(symbols, sector_map, include_unknown=True)
    assert set(exposure.index) == set(symbols)
    assert "Technology" in exposure.columns
    assert "Utilities" in exposure.columns
    assert "Unknown" in exposure.columns
    assert float(exposure.loc["AAA", "Technology"]) == 1.0
    assert float(exposure.loc["BBB", "Unknown"]) == 1.0

    betas = RiskModel.beta_vector(symbols, beta_map, default_beta=1.0)
    assert float(betas.loc["AAA"]) == 1.2
    assert float(betas.loc["BBB"]) == 0.8
    assert float(betas.loc["CCC"]) == 1.0
