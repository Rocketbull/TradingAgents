import json

import pandas as pd

from activeportfolio.core.MyTT import calculate_indicator_from_parquet, get_mytt_indicators_window
from activeportfolio.dataflows import ashare
from activeportfolio.dataflows.config import get_config, set_config
from activeportfolio.dataflows.interface import route_to_vendor
from activeportfolio.dataflows.market_data_store import save_history_parquet


def _sample_history_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    close = pd.Series(range(100, 140), dtype=float)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Adj Close": close,
            "Volume": pd.Series(range(1000, 1040), dtype=float),
        }
    )


def test_ashare_normalize_symbol_variants() -> None:
    assert ashare.normalize_symbol("sh600519") == "SH600519"
    assert ashare.normalize_symbol("600519.XSHG") == "SH600519"
    assert ashare.normalize_symbol("600519.sh") == "SH600519"
    assert ashare.normalize_symbol("000001.XSHE") == "SZ000001"


def test_ashare_download_history_to_parquet_uses_repo_schema(tmp_path, monkeypatch) -> None:
    raw = pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0],
            "close": [10.5, 11.5, 12.5],
            "high": [10.8, 11.8, 12.8],
            "low": [9.8, 10.8, 11.8],
            "volume": [1000.0, 1100.0, 1200.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
    )

    def fake_get_price(code: str, end_date: str, count: int, frequency: str, fields=None):
        assert code == "SH600519"
        assert end_date == "2024-01-03"
        assert frequency == "1d"
        assert count >= 3
        return raw

    monkeypatch.setattr(ashare, "get_price", fake_get_price)

    path = ashare.download_history_to_parquet(
        symbol="600519.XSHG",
        start_date="2024-01-01",
        end_date="2024-01-03",
        root_dir=str(tmp_path),
    )

    saved = pd.read_parquet(path)
    assert list(saved.columns) == ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    assert saved["Adj Close"].tolist() == saved["Close"].tolist()

    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["symbol"] == "SH600519"
    assert metadata["source"] == "ashare"


def test_mytt_can_calculate_from_local_parquet_and_route_via_vendor(tmp_path) -> None:
    history = _sample_history_frame()
    save_history_parquet(
        df=history,
        symbol="SH600519",
        start_date="2024-01-01",
        end_date="2024-02-09",
        root_dir=str(tmp_path),
        source="unit-test",
    )

    macd = calculate_indicator_from_parquet(
        symbol="600519.XSHG",
        indicator="macd",
        start_date="2024-01-10",
        end_date="2024-02-09",
        root_dir=str(tmp_path),
    )
    assert list(macd.columns) == ["Date", "DIF", "DEA", "MACD"]
    assert len(macd) == 31
    assert macd["MACD"].notna().any()

    direct = get_mytt_indicators_window(
        symbol="600519.XSHG",
        indicator="rsi",
        curr_date="2024-02-09",
        look_back_days=5,
        root_dir=str(tmp_path),
    )
    assert "## rsi values from 2024-02-04 to 2024-02-09 for SH600519:" in direct
    assert "2024-02-09:" in direct

    original_config = get_config()
    try:
        set_config({"data_root": str(tmp_path), "tool_vendors": {"get_indicators": "mytt"}})
        routed = route_to_vendor("get_indicators", "600519.XSHG", "rsi", "2024-02-09", 3)
    finally:
        set_config(original_config)

    assert "## rsi values from 2024-02-06 to 2024-02-09 for SH600519:" in routed
