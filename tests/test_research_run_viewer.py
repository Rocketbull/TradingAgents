from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.common.research_run_viewer import (
    discover_run_dirs,
    is_single_row_summary,
    load_run_artifacts,
    multi_row_metric_groups,
    single_row_metric_groups,
)


def test_load_run_artifacts_reads_by_trade_and_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "overnight_demo"
    run_dir.mkdir()
    pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "trade_count": 2,
                "net_total_return": 0.1,
                "net_sharpe": 0.5,
            }
        ]
    ).to_csv(run_dir / "summary.csv", index=False)
    pd.DataFrame(
        [
            {"trade_date": "2024-01-02", "exit_date": "2024-01-03", "net_return": 0.01},
            {"trade_date": "2024-01-03", "exit_date": "2024-01-04", "net_return": -0.02},
        ]
    ).to_csv(run_dir / "by_trade.csv", index=False)
    (run_dir / "params.json").write_text(json.dumps({"symbol": "SPY"}), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps({"run_tag": "overnight_demo"}), encoding="utf-8")

    artifacts = load_run_artifacts(run_dir)

    assert is_single_row_summary(artifacts.summary)
    assert artifacts.by_trade is not None
    assert pd.api.types.is_datetime64_any_dtype(artifacts.by_trade["trade_date"])
    assert artifacts.params["symbol"] == "SPY"
    assert artifacts.manifest["run_tag"] == "overnight_demo"


def test_metric_groups_include_overnight_and_multirow_fields() -> None:
    overnight_summary = pd.DataFrame(
        [{"net_total_return": 0.1, "net_sharpe": 0.5, "trade_count": 10, "net_win_rate": 0.6}]
    )
    row_groups = single_row_metric_groups(overnight_summary)
    assert "net_total_return" in row_groups["Returns"]
    assert "net_sharpe" in row_groups["Risk / Quality"]
    assert "trade_count" in row_groups["Trade Stats"]

    horizon_summary = pd.DataFrame(
        [{"horizon_days": 1, "sharpe": 0.4, "average_ic": 0.02, "average_breadth_proxy": 15.0}]
    )
    multi_groups = multi_row_metric_groups(horizon_summary)
    assert "sharpe" in multi_groups["Performance / IR"]
    assert "average_ic" in multi_groups["IC Diagnostics"]
    assert "average_breadth_proxy" in multi_groups["Implementation / Breadth"]


def test_discover_run_dirs_filters_for_summary_csv(tmp_path: Path) -> None:
    good = tmp_path / "good_run"
    good.mkdir()
    (good / "summary.csv").write_text("a\n1\n", encoding="utf-8")
    bad = tmp_path / "bad_run"
    bad.mkdir()

    discovered = discover_run_dirs(tmp_path)

    assert discovered == [good]
