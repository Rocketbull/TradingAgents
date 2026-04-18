from __future__ import annotations

import pandas as pd

from tradingagents.alpha import AlphaModel
from tradingagents.alpha.signals import TrailingLaggardBandAlpha


def _laggard_frame() -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=260, freq="D")
    data: dict[str, pd.Series] = {}
    for i in range(80):
        symbol = f"S{i:03d}"
        start = 100.0
        end = start * (1.0 - (i / 100.0))
        data[symbol] = pd.Series(
            [start + (end - start) * (t / (len(idx) - 1)) for t in range(len(idx))],
            index=idx,
            dtype=float,
        )
    return pd.DataFrame(data, index=idx)


def test_trailing_laggard_band_alpha_selects_worst_50() -> None:
    closes = _laggard_frame()
    signal = TrailingLaggardBandAlpha(
        name="laggard_1y_worst50",
        lookback_window=252,
        outer_n=50,
        skip_n=0,
    )
    raw = signal.compute(closes)
    selected = set(raw[raw > 0.0].index)

    assert len(selected) == 50
    assert "S079" in selected
    assert "S030" in selected
    assert "S029" not in selected
    assert float(raw.loc["S079"]) > float(raw.loc["S030"]) > 0.0


def test_alpha_model_registry_builds_trailing_laggard_band() -> None:
    closes = _laggard_frame()
    model = AlphaModel.from_config(
        {
            "alpha_signal_registry": [
                {
                    "type": "trailing_laggard_band",
                    "name": "laggard_1y_worst50",
                    "lookback_window": 252,
                    "outer_n": 50,
                    "skip_n": 0,
                }
            ]
        }
    )
    components = model.component_scores(closes)
    assert set(components.columns) == {"laggard_1y_worst50"}
    assert float(components["laggard_1y_worst50"].abs().sum()) > 0.0
    assert int(model.long_lookback) >= 253
