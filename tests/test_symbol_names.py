from __future__ import annotations

import pandas as pd

from research.common import symbol_names


def test_map_symbols_to_stock_names_uses_csi300_names(tmp_path, monkeypatch) -> None:
    weights_path = tmp_path / "csi300_weights.csv"
    pd.DataFrame(
        {
            "symbol": ["SZ000001", "SH600519"],
            "constituent_name": ["平安银行", "贵州茅台"],
            "constituent_name_eng": ["Ping An Bank", "Kweichow Moutai"],
        }
    ).to_csv(weights_path, index=False)

    monkeypatch.setattr(
        symbol_names,
        "_resolve_existing_path",
        lambda *args: weights_path,
    )
    symbol_names.load_symbol_name_table.cache_clear()

    mapped = symbol_names.map_symbols_to_stock_names(["sz000001", "SH600519"])
    assert mapped == {"SZ000001": "平安银行", "SH600519": "贵州茅台"}

    mapped_eng = symbol_names.map_symbols_to_stock_names(
        ["SZ000001", "SH600519"],
        prefer_english=True,
    )
    assert mapped_eng == {"SZ000001": "Ping An Bank", "SH600519": "Kweichow Moutai"}


def test_get_stock_name_falls_back_to_symbol_when_missing(tmp_path, monkeypatch) -> None:
    weights_path = tmp_path / "csi300_weights.csv"
    pd.DataFrame(
        {
            "symbol": ["SZ000001"],
            "constituent_name": ["平安银行"],
            "constituent_name_eng": ["Ping An Bank"],
        }
    ).to_csv(weights_path, index=False)

    monkeypatch.setattr(
        symbol_names,
        "_resolve_existing_path",
        lambda *args: weights_path,
    )
    symbol_names.load_symbol_name_table.cache_clear()

    assert symbol_names.get_stock_name("SZ000001") == "平安银行"
    assert symbol_names.get_stock_name("AAPL") == "AAPL"
    assert symbol_names.get_stock_name("AAPL", fallback_to_symbol=False) is None
