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
            {"type": "trend", "name": "trend_12m_1m", "long_window": 252, "short_window": 21},
            {"type": "breakout", "name": "breakout_52w", "window": 252},
        ],
        "alpha_signals": ["mom_1m", "mom_3m", "mom_6m", "mom_12m", "trend_12m_1m", "breakout_52w"],
        "alpha_corr_penalty": 0.30,
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
