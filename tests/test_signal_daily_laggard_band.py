from __future__ import annotations

import pandas as pd

from research.signal_daily_laggard_band import (
    VariantSpec,
    _build_signal_return_panel,
    _parse_variant_specs,
    _select_laggard_band,
)


def test_parse_variant_specs_deduplicates_entries() -> None:
    specs = _parse_variant_specs("50:0,60:10,50:0")
    assert specs == [VariantSpec(outer_n=50, skip_n=0), VariantSpec(outer_n=60, skip_n=10)]


def test_select_laggard_band_skips_most_extreme_losers() -> None:
    row = pd.Series({f"S{i:03d}": -float(i) / 100.0 for i in range(1, 81)})
    score, signal, meta = _select_laggard_band(row, outer_n=60, skip_n=10)

    selected = set(signal[signal == 1.0].index)
    excluded = set(meta["excluded_symbols"])
    assert len(selected) == 50
    assert len(excluded) == 10
    assert "S080" not in selected
    assert "S071" not in selected
    assert "S070" in selected
    assert "S021" in selected
    assert "S020" not in selected
    assert excluded == {f"S{i:03d}" for i in range(71, 81)}
    assert float(score.loc["S070"]) > float(score.loc["S021"]) > 0.0
    assert float(meta["selected_signal_return_mean"]) > float(meta["excluded_signal_return_mean"])


def test_select_laggard_band_marks_all_available_names() -> None:
    row = pd.Series({"AAA": -0.05, "BBB": -0.04, "CCC": 0.01, "DDD": 0.03})
    score, signal, meta = _select_laggard_band(row, outer_n=3, skip_n=1)

    assert int(meta["available_symbols"]) == 4
    assert int(meta["selected_count"]) == 2
    assert signal.notna().sum() == 4
    assert score.notna().sum() == 4


def test_build_signal_return_panel_ytd_resets_each_year() -> None:
    idx = pd.to_datetime(["2024-12-31", "2025-01-02", "2025-01-03", "2025-01-06"])
    close = pd.DataFrame(
        {
            "AAA": [100.0, 110.0, 121.0, 115.5],
            "BBB": [200.0, 180.0, 171.0, 189.0],
        },
        index=idx,
    )
    out = _build_signal_return_panel(close, signal_return_mode="ytd", signal_lookback_days=1)

    assert abs(float(out.loc[pd.Timestamp("2024-12-31"), "AAA"]) - 0.0) < 1e-12
    assert abs(float(out.loc[pd.Timestamp("2025-01-02"), "AAA"]) - 0.0) < 1e-12
    assert abs(float(out.loc[pd.Timestamp("2025-01-03"), "AAA"]) - 0.10) < 1e-12
    assert abs(float(out.loc[pd.Timestamp("2025-01-06"), "AAA"]) - 0.05) < 1e-12
    assert abs(float(out.loc[pd.Timestamp("2025-01-03"), "BBB"]) + 0.05) < 1e-12
