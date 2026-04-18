from __future__ import annotations

import pandas as pd

from research.sector_momentum_top2_sector import (
    _monthly_rebalance_dates,
    _select_weights_for_date,
)


def test_select_weights_for_date_top2_per_sector() -> None:
    row = pd.Series(
        {
            "AAA": 0.10,
            "BBB": 0.30,
            "CCC": 0.20,
            "DDD": 0.15,
            "EEE": 0.05,
        }
    )
    sectors = {
        "AAA": "Tech",
        "BBB": "Tech",
        "CCC": "Tech",
        "DDD": "Utilities",
        "EEE": "Utilities",
    }
    weights, selected = _select_weights_for_date(row, sectors, top_k_per_sector=2)
    assert set(weights.keys()) == {"BBB", "CCC", "DDD", "EEE"}
    assert abs(sum(weights.values()) - 1.0) < 1e-12
    assert len(selected) == 4


def test_monthly_rebalance_dates_picks_month_end_rows() -> None:
    idx = pd.to_datetime(
        [
            "2025-01-02",
            "2025-01-31",
            "2025-02-03",
            "2025-02-28",
            "2025-03-03",
            "2025-03-31",
        ]
    )
    rebal = _monthly_rebalance_dates(idx)
    assert [d.strftime("%Y-%m-%d") for d in rebal] == [
        "2025-01-31",
        "2025-02-28",
        "2025-03-31",
    ]
