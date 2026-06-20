from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.download_macro_data import build_download_plan, regime_default_series_ids


def test_regime_default_series_ids_reads_macro_config_keys() -> None:
    config = {
        "regime_macro_unemployment_series_id": "UNRATE",
        "regime_macro_inflation_series_id": "CPIAUCSL",
        "regime_macro_growth_series_id": "INDPRO",
        "regime_macro_curve_series_id": "T10Y2Y",
        "regime_macro_policy_series_id": "FEDFUNDS",
        "regime_macro_stress_series_id": "VIXCLS",
    }

    assert regime_default_series_ids(config) == [
        "UNRATE",
        "CPIAUCSL",
        "INDPRO",
        "T10Y2Y",
        "FEDFUNDS",
        "VIXCLS",
    ]


def test_build_download_plan_merges_defaults_and_cli_series(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(
        json.dumps(
            {
                "regime_macro_data_root": "data/custom_macro",
                "regime_macro_lookback_days": 900,
                "regime_macro_curve_series_id": "DGS10",
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        config_json=str(path),
        series=["UNRATE", "DEXUSEU"],
        regime_defaults=True,
        end_date="2026-06-20",
        lookback_days=None,
        out_dir=None,
        continue_on_error=False,
    )

    series_ids, end_date, lookback_days, out_dir = build_download_plan(args)

    assert series_ids == [
        "UNRATE",
        "CPIAUCSL",
        "INDPRO",
        "DGS10",
        "FEDFUNDS",
        "VIXCLS",
        "DEXUSEU",
    ]
    assert end_date == "2026-06-20"
    assert lookback_days == 900
    assert out_dir == "data/custom_macro"


def test_build_download_plan_requires_selected_series() -> None:
    args = argparse.Namespace(
        config_json=None,
        series=None,
        regime_defaults=False,
        end_date="2026-06-20",
        lookback_days=365,
        out_dir="data/macro/fred",
        continue_on_error=False,
    )

    try:
        build_download_plan(args)
    except ValueError as exc:
        assert "No FRED series selected" in str(exc)
    else:
        raise AssertionError("Expected ValueError when no series are selected")
