from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path

from tools.refresh_sp500_backtest_inputs import (
    DEFAULT_MARKET_START_DATE,
    build_market_symbol_list,
    parse_args,
    resolve_market_window,
    run_refresh_pipeline,
    write_sp500_symbol_outputs,
)


def test_build_market_symbol_list_deduplicates_and_normalizes() -> None:
    symbols = build_market_symbol_list(
        sp500_symbols=["aapl", "msft"],
        benchmark_symbol="spy",
        extra_symbols=["btc-usd", "MSFT", "brk.b"],
    )
    assert symbols == ["AAPL", "MSFT", "SPY", "BTC-USD", "BRK-B"]


def test_write_sp500_symbol_outputs_creates_current_and_snapshot_files(tmp_path: Path) -> None:
    outputs = write_sp500_symbol_outputs(
        symbols=["AAPL", "MSFT"],
        symbols_out=tmp_path / "current" / "sp500_symbols.txt",
        snapshot_dir=tmp_path / "snapshots",
        snapshot_date="2026-03-21",
    )

    symbols_path = Path(outputs["symbols_file"])
    metadata_path = Path(outputs["symbols_metadata"])
    snapshot_path = Path(outputs["snapshot_csv"])

    assert symbols_path.read_text(encoding="utf-8") == "AAPL\nMSFT\n"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["symbol_count"] == 2
    assert snapshot_path.name == "sp500_membership_2026-03-21.csv"
    snapshot_text = snapshot_path.read_text(encoding="utf-8")
    assert "AAPL" in snapshot_text
    assert "MSFT" in snapshot_text


def test_run_refresh_pipeline_executes_steps_in_order(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_fetch_sp500_symbols() -> list[str]:
        calls.append("fetch")
        return ["AAPL", "MSFT"]

    def fake_write_sp500_symbol_outputs(**kwargs):
        calls.append("symbols")
        return {
            "symbols_file": str(tmp_path / "sp500_symbols.txt"),
            "symbols_metadata": str(tmp_path / "sp500_symbols.metadata.json"),
            "snapshot_csv": str(tmp_path / "sp500_membership_2026-03-21.csv"),
        }

    def fake_refresh_market_history(**kwargs):
        calls.append("market")
        assert kwargs["symbols"] == ["AAPL", "MSFT", "SPY", "BTC-USD"]
        assert kwargs["start_date"] == "2026-03-01"
        assert kwargs["end_date"] == "2026-03-21"
        return {"symbols_failed": 0}

    def fake_refresh_fundamentals(**kwargs):
        calls.append("fundamentals")
        assert kwargs["symbols"] == ["AAPL", "MSFT"]
        return {"symbols_failed": 0}

    monkeypatch.setattr(
        "tools.refresh_sp500_backtest_inputs.fetch_sp500_symbols",
        fake_fetch_sp500_symbols,
    )
    monkeypatch.setattr(
        "tools.refresh_sp500_backtest_inputs.write_sp500_symbol_outputs",
        fake_write_sp500_symbol_outputs,
    )
    monkeypatch.setattr(
        "tools.refresh_sp500_backtest_inputs.refresh_market_history",
        fake_refresh_market_history,
    )
    monkeypatch.setattr(
        "tools.refresh_sp500_backtest_inputs.refresh_fundamentals",
        fake_refresh_fundamentals,
    )

    args = Namespace(
        symbols_out=str(tmp_path / "symbols.txt"),
        snapshot_dir=str(tmp_path / "snapshots"),
        snapshot_date="2026-03-21",
        benchmark_symbol="SPY",
        extra_symbol=["BTC-USD"],
        start_date="2026-03-01",
        end_date="2026-03-21",
        years=5,
        market_out_dir=str(tmp_path / "market"),
        overwrite_market=True,
        fundamentals_out_dir=str(tmp_path / "fundamentals"),
        fundamentals_sleep_seconds=0.0,
        overwrite_fundamentals_latest=True,
        universe_limit=0,
        skip_market_data=False,
        skip_fundamentals=False,
    )

    summary = run_refresh_pipeline(args)
    assert calls == ["fetch", "symbols", "market", "fundamentals"]
    assert summary["has_errors"] is False
    assert summary["sp500_symbol_count"] == 2


def test_resolve_market_window_requires_complete_explicit_range() -> None:
    try:
        resolve_market_window("2026-03-01", None, years=5)
    except ValueError as exc:
        assert "Provide both --start-date and --end-date together" in str(exc)
    else:
        raise AssertionError("Expected ValueError for incomplete explicit date range")


def test_parse_args_defaults_to_fixed_market_start(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["refresh_sp500_backtest_inputs.py", "--skip-fundamentals"])

    args = parse_args()

    assert args.start_date == DEFAULT_MARKET_START_DATE
