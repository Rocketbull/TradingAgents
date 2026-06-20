from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


ALPHA_PROFILES: Dict[str, Dict[str, Any]] = {
    "conservative": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "momentum", "name": "mom_6m", "window": 126},
            {"type": "low_vol", "name": "low_vol", "window": 60},
            {"type": "downside_vol", "name": "downside_vol", "window": 60},
            {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
        ],
        "alpha_signals": ["mom_3m", "mom_6m", "low_vol", "downside_vol", "trend_12m_1m"],
        "alpha_corr_penalty": 0.45,
    },
    "momentum_heavy": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "momentum", "name": "mom_6m", "window": 126},
            {"type": "momentum", "name": "mom_12m", "window": 252},
            {"type": "momentum_skip_recent", "name": "mom_12m_skip_1m", "long_window": 252, "skip_window": 21},
            {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
            {"type": "breakout", "name": "breakout_52w", "window": 252},
        ],
        "alpha_signals": [
            "mom_1m",
            "mom_3m",
            "mom_6m",
            "mom_12m",
            "mom_12m_skip_1m",
            "trend_12m_1m",
            "breakout_52w",
        ],
        "alpha_corr_penalty": 0.30,
    },
    "sp500_momentum_legacy": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "momentum", "name": "mom_6m", "window": 126},
            {"type": "momentum", "name": "mom_12m", "window": 252},
            {"type": "momentum_skip_recent", "name": "mom_12m_skip_1m", "long_window": 252, "skip_window": 21},
            {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
            {"type": "breakout", "name": "breakout_52w", "window": 252},
        ],
        "alpha_signals": [
            "mom_1m",
            "mom_3m",
            "mom_6m",
            "mom_12m",
            "mom_12m_skip_1m",
            "trend_12m_1m",
            "breakout_52w",
        ],
        "alpha_corr_penalty": 0.30,
        "alpha_weight_smoothing": 0.25,
        "alpha_max_signal_weight": 0.35,
        "ic_ewm_decay": 0.85,
        "ic_gate_min_mean": None,
        "ic_gate_use_abs_mean": False,
        "ic_gate_min_tstat": None,
        "ic_gate_min_hit_rate": None,
        "ic_gate_min_samples": 8,
    },
    "sp500_gated_vol_confirmed": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "momentum", "name": "mom_6m", "window": 126},
            {"type": "momentum", "name": "mom_12m", "window": 252},
            {"type": "momentum_skip_recent", "name": "mom_12m_skip_1m", "long_window": 252, "skip_window": 21},
            {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
            {
                "type": "volume_confirmed_momentum",
                "name": "vol_confirmed_mom_1m",
                "momentum_window": 21,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
        ],
        "alpha_signals": [
            "mom_1m",
            "mom_3m",
            "mom_6m",
            "mom_12m",
            "mom_12m_skip_1m",
            "trend_12m_1m",
            "vol_confirmed_mom_1m",
        ],
        "ic_weighting_mode": "positive",
        "alpha_corr_penalty": 0.40,
        "alpha_weight_smoothing": 0.35,
        "alpha_max_signal_weight": 0.25,
        "ic_ewm_decay": 0.85,
        "ic_gate_min_mean": 0.005,
        "ic_gate_use_abs_mean": False,
        "ic_gate_min_tstat": None,
        "ic_gate_min_hit_rate": 0.52,
        "ic_gate_min_samples": 12,
    },
    "sp500_gated_vol_confirmed_te009": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "momentum", "name": "mom_6m", "window": 126},
            {"type": "momentum", "name": "mom_12m", "window": 252},
            {"type": "momentum_skip_recent", "name": "mom_12m_skip_1m", "long_window": 252, "skip_window": 21},
            {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
            {
                "type": "volume_confirmed_momentum",
                "name": "vol_confirmed_mom_1m",
                "momentum_window": 21,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
        ],
        "alpha_signals": [
            "mom_1m",
            "mom_3m",
            "mom_6m",
            "mom_12m",
            "mom_12m_skip_1m",
            "trend_12m_1m",
            "vol_confirmed_mom_1m",
        ],
        "ic_weighting_mode": "positive",
        "alpha_corr_penalty": 0.40,
        "alpha_weight_smoothing": 0.25,
        "alpha_max_signal_weight": 0.25,
        "ic_ewm_decay": 0.85,
        "ic_gate_min_mean": 0.005,
        "ic_gate_use_abs_mean": False,
        "ic_gate_min_tstat": None,
        "ic_gate_min_hit_rate": 0.52,
        "ic_gate_min_samples": 12,
        "tracking_error_target": 0.09,
    },
    "mean_reversion_heavy": {
        "alpha_signal_registry": [
            {"type": "reversal", "name": "rev_1w", "window": 5},
            {"type": "reversal", "name": "rev_1m", "window": 21},
            {"type": "low_vol", "name": "low_vol", "window": 60},
            {"type": "downside_vol", "name": "downside_vol", "window": 60},
            {"type": "momentum", "name": "mom_3m", "window": 63},
        ],
        "alpha_signals": ["rev_1w", "rev_1m", "low_vol", "downside_vol", "mom_3m"],
        "ic_weighting_mode": "signed",
        "alpha_corr_penalty": 0.50,
    },
    "risk_on_crypto_anchor": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "momentum", "name": "mom_6m", "window": 126},
            {"type": "reversal", "name": "rev_1w", "window": 5},
            {"type": "low_vol", "name": "low_vol", "window": 60},
            {
                "type": "btc_gld_corr",
                "name": "btc_gld_corr",
                "lookback_window": 120,
                "risk_symbol": "BTC-USD",
                "defensive_symbol": "GLD",
                "defensive_weight": 1.0,
                "risk_weight": 1.0,
                "flip_sign": True,
            },
        ],
        "alpha_signals": ["mom_1m", "mom_3m", "mom_6m", "rev_1w", "low_vol", "btc_gld_corr"],
        "alpha_corr_penalty": 0.35,
    },
    "diversified_sp500_v1": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "reversal", "name": "rev_1m", "window": 21},
            {"type": "low_vol", "name": "low_vol", "window": 60},
            {"type": "vol_adj_momentum", "name": "vol_adj_mom_3m", "momentum_window": 63, "vol_window": 21},
            {"type": "range_position", "name": "range_pos_3m", "window": 63},
            {
                "type": "volume_shock",
                "name": "volume_shock_1w",
                "price_window": 5,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
        ],
        "alpha_signals": ["mom_3m", "rev_1m", "low_vol", "vol_adj_mom_3m", "range_pos_3m", "volume_shock_1w"],
        "alpha_corr_penalty": 0.40,
    },
    "diversified_sp500_v2_tilt": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "momentum", "name": "mom_6m", "window": 126},
            {"type": "reversal", "name": "rev_1m", "window": 21},
            {"type": "vol_adj_momentum", "name": "vol_adj_mom_3m", "momentum_window": 63, "vol_window": 21},
            {
                "type": "volume_shock",
                "name": "volume_shock_1w",
                "price_window": 5,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
        ],
        "alpha_signals": ["mom_3m", "mom_6m", "rev_1m", "vol_adj_mom_3m", "volume_shock_1w"],
        "alpha_corr_penalty": 0.35,
    },
    "csi300_hybrid_v1": {
        "alpha_signal_registry": [
            {"type": "reversal", "name": "rev_1w", "window": 5},
            {"type": "reversal", "name": "rev_1m", "window": 21},
            {"type": "low_vol", "name": "low_vol", "window": 60},
            {"type": "downside_vol", "name": "downside_vol", "window": 60},
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "vol_adj_momentum", "name": "vol_adj_mom_3m", "momentum_window": 63, "vol_window": 21},
            {
                "type": "volume_confirmed_momentum",
                "name": "vol_confirmed_mom_1m",
                "momentum_window": 21,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
            {
                "type": "volume_shock",
                "name": "volume_shock_1w",
                "price_window": 5,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
        ],
        "alpha_signals": [
            "rev_1w",
            "rev_1m",
            "low_vol",
            "downside_vol",
            "mom_1m",
            "mom_3m",
            "vol_adj_mom_3m",
            "vol_confirmed_mom_1m",
            "volume_shock_1w",
        ],
        "ic_weighting_mode": "positive",
        "alpha_corr_penalty": 0.45,
    },
    "csi500_reversal_liquidity_v1": {
        "alpha_signal_registry": [
            {"type": "reversal", "name": "rev_1w", "window": 5},
            {"type": "reversal", "name": "rev_1m", "window": 21},
            {"type": "low_vol", "name": "low_vol", "window": 60},
            {"type": "downside_vol", "name": "downside_vol", "window": 60},
            {"type": "range_position", "name": "range_pos_3m", "window": 63},
            {
                "type": "volume_shock",
                "name": "volume_shock_1w",
                "price_window": 5,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
        ],
        "alpha_signals": [
            "rev_1w",
            "rev_1m",
            "low_vol",
            "downside_vol",
            "range_pos_3m",
            "volume_shock_1w",
        ],
        "ic_weighting_mode": "positive",
        "alpha_corr_penalty": 0.45,
    },
    "csi500_volume_breakout_v1": {
        "alpha_signal_registry": [
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "vol_adj_momentum", "name": "vol_adj_mom_3m", "momentum_window": 63, "vol_window": 21},
            {
                "type": "volume_confirmed_momentum",
                "name": "vol_confirmed_mom_1m",
                "momentum_window": 21,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
            {
                "type": "volume_shock",
                "name": "volume_shock_1w",
                "price_window": 5,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
            {
                "type": "flat_vol_breakout",
                "name": "flat_breakout_20d",
                "flat_window": 60,
                "flat_max_abs_return": 0.15,
                "price_window": 20,
                "price_ratio_min": 1.08,
                "vol_short_window": 5,
                "vol_long_window": 20,
                "vol_ratio_min": 1.35,
            },
        ],
        "alpha_signals": [
            "mom_1m",
            "mom_3m",
            "vol_adj_mom_3m",
            "vol_confirmed_mom_1m",
            "volume_shock_1w",
            "flat_breakout_20d",
        ],
        "ic_weighting_mode": "positive",
        "alpha_corr_penalty": 0.40,
    },
    "csi500_hybrid_v2": {
        "alpha_signal_registry": [
            {"type": "reversal", "name": "rev_1w", "window": 5},
            {"type": "reversal", "name": "rev_1m", "window": 21},
            {"type": "low_vol", "name": "low_vol", "window": 60},
            {"type": "momentum", "name": "mom_1m", "window": 21},
            {"type": "momentum", "name": "mom_3m", "window": 63},
            {"type": "vol_adj_momentum", "name": "vol_adj_mom_3m", "momentum_window": 63, "vol_window": 21},
            {"type": "range_position", "name": "range_pos_3m", "window": 63},
            {
                "type": "volume_confirmed_momentum",
                "name": "vol_confirmed_mom_1m",
                "momentum_window": 21,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
            {
                "type": "volume_shock",
                "name": "volume_shock_1w",
                "price_window": 5,
                "vol_short_window": 5,
                "vol_long_window": 20,
            },
            {
                "type": "flat_vol_breakout",
                "name": "flat_breakout_20d",
                "flat_window": 60,
                "flat_max_abs_return": 0.15,
                "price_window": 20,
                "price_ratio_min": 1.08,
                "vol_short_window": 5,
                "vol_long_window": 20,
                "vol_ratio_min": 1.35,
            },
        ],
        "alpha_signals": [
            "rev_1w",
            "rev_1m",
            "low_vol",
            "mom_1m",
            "mom_3m",
            "vol_adj_mom_3m",
            "range_pos_3m",
            "vol_confirmed_mom_1m",
            "volume_shock_1w",
            "flat_breakout_20d",
        ],
        "ic_weighting_mode": "positive",
        "alpha_corr_penalty": 0.40,
        "alpha_weight_smoothing": 0.35,
        "alpha_max_signal_weight": 0.25,
    },
}


def list_alpha_profiles() -> list[str]:
    return sorted(ALPHA_PROFILES.keys())


def get_alpha_profile(name: str) -> Dict[str, Any]:
    key = str(name).strip().lower()
    if key not in ALPHA_PROFILES:
        raise ValueError(f"Unknown alpha profile '{name}'. Available: {list_alpha_profiles()}")
    return deepcopy(ALPHA_PROFILES[key])


def apply_alpha_profile(config: Dict[str, Any], profile_name: str, overwrite: bool = True) -> Dict[str, Any]:
    """
    Return a config dict with alpha profile settings applied.

    Args:
        config: base configuration to extend.
        profile_name: one of list_alpha_profiles().
        overwrite: if False, only set keys absent in config.
    """
    out = dict(config)
    profile = get_alpha_profile(profile_name)
    if overwrite:
        out.update(profile)
        return out

    for k, v in profile.items():
        if k not in out:
            out[k] = v
    return out
