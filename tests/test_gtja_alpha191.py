from __future__ import annotations

from pathlib import Path

import pandas as pd

from activeportfolio.alpha.gtja_alpha191 import GTJA_191, get_index_stocks, get_price
from activeportfolio.dataflows.market_data_store import save_history_parquet


def _write_history(root_dir: Path, symbol: str) -> None:
    history = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=6, freq="D"),
            "Open": [10, 11, 12, 13, 14, 15],
            "High": [11, 12, 13, 14, 15, 16],
            "Low": [9, 10, 11, 12, 13, 14],
            "Close": [10.5, 11.5, 12.5, 13.5, 14.5, 15.5],
            "Adj Close": [10.5, 11.5, 12.5, 13.5, 14.5, 15.5],
            "Volume": [100, 110, 120, 130, 140, 150],
        }
    )
    save_history_parquet(
        df=history,
        symbol=symbol,
        start_date="2024-01-01",
        end_date="2024-01-06",
        root_dir=str(root_dir),
    )


def test_get_index_stocks_spy_uses_local_symbol_file(tmp_path: Path) -> None:
    symbol_file = tmp_path / "sp500_symbols.txt"
    symbol_file.write_text("AAPL\nMSFT\nSPY\n", encoding="utf-8")

    symbols = get_index_stocks("SPY", symbol_file=symbol_file)

    assert symbols == ["AAPL", "MSFT"]


def test_get_price_reads_local_parquet_and_marks_missing_avg_price(tmp_path: Path) -> None:
    _write_history(tmp_path, "AAPL")
    _write_history(tmp_path, "MSFT")

    price = get_price(
        ["AAPL", "MSFT"],
        end_date="2024-01-06",
        frequency="1d",
        fields=["open", "close", "avg_price", "prev_close", "turnover"],
        count=3,
        is_panel=1,
        root_dir=tmp_path,
    )

    assert price.attrs["missing_fields"] == ["avg_price"]
    assert list(price.columns) == ["AAPL", "MSFT"]
    assert price.loc[("open", pd.Timestamp("2024-01-04")), "AAPL"] == 13
    assert price.loc[("prev_close", pd.Timestamp("2024-01-04")), "AAPL"] == 12.5
    assert price.loc[("turnover", pd.Timestamp("2024-01-06")), "AAPL"] == 15.5 * 150
    assert pd.isna(price.loc[("avg_price", pd.Timestamp("2024-01-06")), "AAPL"])


def test_gtja191_tracks_avg_price_affected_alphas(tmp_path: Path) -> None:
    for symbol in ["SPY", "AAPL", "MSFT"]:
        _write_history(tmp_path, symbol)

    symbol_file = tmp_path / "sp500_symbols.txt"
    symbol_file.write_text("AAPL\nMSFT\n", encoding="utf-8")

    alpha = GTJA_191(
        end_date="2024-01-06",
        index="SPY",
        symbol_file=symbol_file,
        root_dir=tmp_path,
    )

    assert alpha.benchmark_symbol == "SPY"
    assert "avg_price" in alpha.missing_data_fields
    assert "alpha_007" in alpha.avg_price_affected_alphas
    assert alpha.avg_price.isna().all().all()
    assert alpha.data_warnings
