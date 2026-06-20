from __future__ import annotations

from activeportfolio.default_config import DEFAULT_CONFIG
from tools.run_ab_backtest_pair import resolve_config


def test_resolve_config_applies_named_alpha_profile_before_warmup_logic() -> None:
    base = DEFAULT_CONFIG.copy()
    resolved = resolve_config(base, {"alpha_profile": "csi500_volume_breakout_v1"})

    assert resolved["alpha_profile"] == "csi500_volume_breakout_v1"
    assert "alpha_signal_registry" in resolved
    assert "flat_breakout_20d" in resolved["alpha_signals"]
    assert any(
        spec.get("name") == "flat_breakout_20d"
        for spec in resolved["alpha_signal_registry"]
    )
