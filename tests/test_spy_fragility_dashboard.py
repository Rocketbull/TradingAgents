from __future__ import annotations

import pandas as pd

from tools.spy_fragility_dashboard import build_summary, classify_fragility_regime, summarize_signal


def test_classify_fragility_regime_uses_macro_watch_or_event_risk_off() -> None:
    index = pd.date_range("2026-01-01", periods=5)
    rule_scores = pd.Series([0, 1, 2, 3, 0], index=index)
    macro_scores = pd.Series([0, 0, 1, 0, 2], index=index)

    regimes = classify_fragility_regime(rule_scores, macro_scores)

    assert regimes.tolist() == ["normal", "watch", "watch", "risk_off", "risk_off"]


def test_summarize_signal_uses_forward_path_tail_rates() -> None:
    signals = pd.DataFrame(
        {
            "spy_ret": [-0.01, 0.01, -0.02],
            "fwd_1d_tail": [True, False, False],
            "fwd_1d_min_ret": [-0.02, 0.0, -0.01],
            "fwd_1d_ret": [-0.02, 0.0, -0.01],
            "fwd_3d_tail": [True, False, False],
            "fwd_3d_min_ret": [-0.03, -0.01, -0.01],
            "fwd_3d_ret": [-0.01, 0.01, 0.0],
            "fwd_5d_tail": [True, False, True],
            "fwd_5d_min_ret": [-0.04, -0.01, -0.05],
            "fwd_5d_ret": [-0.02, 0.02, -0.01],
            "fwd_10d_tail": [False, True, True],
            "fwd_10d_min_ret": [-0.02, -0.05, -0.06],
            "fwd_10d_ret": [0.01, -0.02, -0.01],
        },
        index=pd.date_range("2026-01-01", periods=3),
    )

    row = summarize_signal(signals, signals["spy_ret"] < 0, "spy_down")

    assert row["days"] == 2
    assert row["5d_path_tail_rate"] == 1.0
    assert row["10d_path_tail_rate"] == 0.5
    assert row["5d_avg_min_ret"] == -0.045


def test_build_summary_adds_expected_lift_columns() -> None:
    index = pd.date_range("2026-01-01", periods=4)
    signals = pd.DataFrame(
        {
            "spy_ret": [-0.01, 0.01, -0.02, 0.005],
            "breadth_z": [0.0, 1.2, 0.5, 1.5],
            "breadth_break": [False, False, True, False],
            "rule_regime": ["normal", "watch", "risk_off", "normal"],
            "macro_regime": ["normal", "watch", "risk_off", "normal"],
            "fragility_regime_v1": ["normal", "watch", "risk_off", "normal"],
            "fragility_regime": ["normal", "watch", "risk_off", "normal"],
            "rule_stress_score": [0, 1, 3, 0],
            "macro_stress_score": [0, 2, 3, 0],
            "fwd_1d_tail": [False, False, True, False],
            "fwd_1d_min_ret": [-0.01, -0.01, -0.02, 0.0],
            "fwd_1d_ret": [-0.01, -0.01, -0.02, 0.0],
            "fwd_3d_tail": [False, False, True, False],
            "fwd_3d_min_ret": [-0.01, -0.01, -0.03, 0.0],
            "fwd_3d_ret": [0.0, -0.01, -0.02, 0.0],
            "fwd_5d_tail": [False, False, True, False],
            "fwd_5d_min_ret": [-0.01, -0.01, -0.04, 0.0],
            "fwd_5d_ret": [0.0, -0.01, -0.02, 0.0],
            "fwd_10d_tail": [False, False, True, False],
            "fwd_10d_min_ret": [-0.01, -0.01, -0.05, 0.0],
            "fwd_10d_ret": [0.0, -0.01, -0.02, 0.0],
        },
        index=index,
    )

    summary, score_buckets = build_summary(signals)

    assert "5d_tail_lift_vs_all" in summary.columns
    assert "5d_tail_lift_vs_spy_down" in summary.columns
    assert set(score_buckets["signal"]) >= {"event_score_0", "event_score_1", "event_score_3"}
