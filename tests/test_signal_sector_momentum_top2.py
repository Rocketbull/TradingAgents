from __future__ import annotations

import pandas as pd

from research.signal_sector_momentum_top2 import _sector_relative_scores_and_signal


def test_sector_relative_scores_and_signal_top2() -> None:
    momentum = pd.Series({"AAA": 0.10, "BBB": 0.30, "CCC": 0.20, "DDD": 0.40, "EEE": 0.05})
    sector_map = {
        "AAA": "Tech",
        "BBB": "Tech",
        "CCC": "Tech",
        "DDD": "Utilities",
        "EEE": "Utilities",
    }
    scores, signal = _sector_relative_scores_and_signal(momentum, sector_map, top_k_per_sector=2)
    # Tech top2: BBB, CCC. Utilities top2 includes both names because only 2 names exist.
    assert set(signal[signal > 0].index) == {"BBB", "CCC", "DDD", "EEE"}
    assert float(scores["BBB"]) >= float(scores["CCC"]) >= float(scores["AAA"])
