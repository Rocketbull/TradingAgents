from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tools.csi300_symbols import normalize_csi300_symbol, normalize_csi300_weights, write_csi300_outputs


def test_normalize_csi300_symbol() -> None:
    assert normalize_csi300_symbol("1", "深圳证券交易所") == "SZ000001"
    assert normalize_csi300_symbol("600519", "Shanghai Stock Exchange") == "SH600519"


def test_normalize_csi300_weights() -> None:
    raw = pd.DataFrame(
        {
            "日期Date": [20260227, 20260227],
            "指数代码 Index Code": [300, 300],
            "指数名称 Index Name": ["沪深300", "沪深300"],
            "指数英文名称Index Name(Eng)": ["CSI 300", "CSI 300"],
            "成份券代码Constituent Code": [1, 600519],
            "成份券名称Constituent Name": ["平安银行", "贵州茅台"],
            "成份券英文名称Constituent Name(Eng)": ["Ping An Bank", "Kweichow Moutai"],
            "交易所Exchange": ["深圳证券交易所", "上海证券交易所"],
            "交易所英文名称Exchange(Eng)": [
                "Shenzhen Stock Exchange",
                "Shanghai Stock Exchange",
            ],
            "权重(%)weight": [0.411, 4.2],
        }
    )

    weights = normalize_csi300_weights(raw)
    assert weights["asof_date"].tolist() == ["2026-02-27", "2026-02-27"]
    assert weights["index_code"].tolist() == ["000300", "000300"]
    assert weights["symbol"].tolist() == ["SZ000001", "SH600519"]
    assert weights["weight_pct"].tolist() == [0.411, 4.2]


def test_write_csi300_outputs(tmp_path: Path) -> None:
    weights = pd.DataFrame(
        {
            "asof_date": ["2026-02-27", "2026-02-27"],
            "index_code": ["000300", "000300"],
            "index_name": ["沪深300", "沪深300"],
            "index_name_eng": ["CSI 300", "CSI 300"],
            "symbol": ["SZ000001", "SH600519"],
            "constituent_code": ["000001", "600519"],
            "constituent_name": ["平安银行", "贵州茅台"],
            "constituent_name_eng": ["Ping An Bank", "Kweichow Moutai"],
            "exchange": ["深圳证券交易所", "上海证券交易所"],
            "exchange_eng": ["Shenzhen Stock Exchange", "Shanghai Stock Exchange"],
            "weight_pct": [0.411, 4.2],
            "source": ["official", "official"],
            "detail_page": ["detail", "detail"],
        }
    )

    paths = write_csi300_outputs(
        weights=weights,
        out=str(tmp_path / "current" / "csi300_symbols.txt"),
        weights_out=str(tmp_path / "current" / "csi300_weights.csv"),
        snapshot_dir=str(tmp_path / "snapshots"),
        weights_snapshot_dir=str(tmp_path / "weights"),
    )

    assert (tmp_path / "current" / "csi300_symbols.txt").read_text(encoding="utf-8") == (
        "SZ000001\nSH600519\n"
    )
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert metadata["asof_date"] == "2026-02-27"
    assert metadata["symbol_count"] == 2

    snapshot = pd.read_csv(tmp_path / "snapshots" / "csi300_membership_2026-02-27.csv")
    assert snapshot["symbol"].tolist() == ["SZ000001", "SH600519"]

    weights_snapshot = pd.read_csv(tmp_path / "weights" / "csi300_weights_2026-02-27.csv")
    assert weights_snapshot["weight_pct"].tolist() == [0.411, 4.2]
