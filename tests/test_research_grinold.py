from __future__ import annotations

import numpy as np
import pandas as pd

from research.common import GrinoldDiagnostics


def _toy_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    idx = pd.date_range("2025-01-01", periods=40, freq="D")
    cols = ["A", "B", "C", "D"]
    score = pd.DataFrame(
        {
            "A": np.linspace(1.0, 2.0, len(idx)),
            "B": np.linspace(0.5, 1.5, len(idx)),
            "C": np.linspace(-0.5, 0.2, len(idx)),
            "D": np.linspace(-1.0, -0.2, len(idx)),
        },
        index=idx,
    )
    signal = (score.rank(axis=1, pct=True) >= 0.75).astype(float)
    fwd = score.shift(-1).sub(score).reindex(columns=cols).fillna(0.0) / 100.0
    return signal, score, fwd


def test_grinold_ic_gate_columns_present():
    signal, score, fwd = _toy_frames()
    d = GrinoldDiagnostics(
        weighting_mode="long_only",
        top_k=2,
        ic_gate_lookback=10,
        ic_gate_min_mean=0.01,
        ic_gate_min_tstat=0.5,
        ic_gate_min_hit_rate=0.50,
        ic_gate_min_samples=6,
    )
    summary, by_date = d.evaluate_horizon(signal=signal, score=score, fwd_ret=fwd, horizon_days=1)

    for k in [
        "ic_gate_lookback",
        "ic_gate_min_samples",
        "ic_gate_min_mean",
        "ic_gate_min_tstat",
        "ic_gate_min_hit_rate",
        "ic_gate_effective_points",
        "ic_gate_pass_rate",
        "ic_gate_fallback_rate",
    ]:
        assert k in summary

    for c in [
        "ic_hist_n",
        "ic_hist_mean",
        "ic_hist_tstat",
        "ic_hist_hit_rate",
        "ic_gate_is_effective",
        "ic_gate_pass",
        "ic_gate_fallback",
    ]:
        assert c in by_date.columns
