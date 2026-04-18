from __future__ import annotations

from pathlib import Path

from tools.demo_hypothesis_threshold import _available_ranges, _resolve_dates


def _touch_history(root: Path, symbol: str, start: str, end: str) -> None:
    d = root / symbol
    d.mkdir(parents=True, exist_ok=True)
    (d / f"history_{start}_{end}.parquet").write_text("demo", encoding="utf-8")


def test_resolve_dates_uses_requested_when_available(tmp_path: Path) -> None:
    _touch_history(tmp_path, "SPY", "2021-01-01", "2022-01-01")
    _touch_history(tmp_path, "TSLA", "2021-01-01", "2022-01-01")
    got = _resolve_dates(
        data_dir=tmp_path,
        spy_symbol="SPY",
        lead_symbol="TSLA",
        requested_start="2021-01-01",
        requested_end="2022-01-01",
        auto_resolve=True,
    )
    assert got == ("2021-01-01", "2022-01-01")


def test_resolve_dates_falls_back_to_latest_common_range(tmp_path: Path) -> None:
    _touch_history(tmp_path, "SPY", "2020-01-01", "2021-01-01")
    _touch_history(tmp_path, "SPY", "2021-01-01", "2022-01-01")
    _touch_history(tmp_path, "TSLA", "2020-01-01", "2021-01-01")
    _touch_history(tmp_path, "TSLA", "2021-01-01", "2022-01-01")
    got = _resolve_dates(
        data_dir=tmp_path,
        spy_symbol="SPY",
        lead_symbol="TSLA",
        requested_start="2019-01-01",
        requested_end="2019-12-31",
        auto_resolve=True,
    )
    assert got == ("2021-01-01", "2022-01-01")


def test_available_ranges_ignores_non_matching_files(tmp_path: Path) -> None:
    d = tmp_path / "SPY"
    d.mkdir(parents=True, exist_ok=True)
    (d / "not_history.parquet").write_text("x", encoding="utf-8")
    (d / "history_2021-01-01_2022-01-01.parquet").write_text("x", encoding="utf-8")
    assert _available_ranges(tmp_path, "SPY") == {("2021-01-01", "2022-01-01")}
