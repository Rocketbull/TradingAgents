from __future__ import annotations

import pandas as pd
import pytest

from tools.backtest_position_report import build_position_report


def test_build_position_report_top20_and_sector_rollup() -> None:
    weights = pd.DataFrame(
        [
            {"trade_date": "2026-03-31", "AAA": 0.40, "BBB": 0.35, "CCC": 0.25},
            {"trade_date": "2026-04-30", "AAA": 0.30, "BBB": 0.20, "CCC": 0.50},
        ]
    )
    sector_map = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "sector": ["Tech", "Energy", "Tech"],
        }
    )

    report = build_position_report(weights, sector_map)

    latest_top = report["latest_top20"]
    assert latest_top.iloc[0]["symbol"] == "CCC"
    assert latest_top.iloc[0]["delta"] == 0.25

    inc = report["top_increases"]
    dec = report["top_decreases"]
    assert inc.iloc[0]["symbol"] == "CCC"
    assert dec.iloc[0]["symbol"] == "BBB"

    sector_rollup = report["sector_rollup"].set_index("sector")
    assert sector_rollup.loc["Tech", "latest_weight"] == 0.80
    assert sector_rollup.loc["Tech", "prev_weight"] == 0.65
    assert sector_rollup.loc["Tech", "delta"] == pytest.approx(0.15)
