from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from tools.csi500_symbols import fetch_csi500_symbols, write_csi500_outputs
from tools.csi300_symbols import normalize_csi300_weights


def test_normalize_csi500_weights_from_shared_schema() -> None:
    raw = pd.DataFrame(
        {
            "日期Date": [20260227, 20260227],
            "指数代码 Index Code": [905, 905],
            "指数名称 Index Name": ["中证500", "中证500"],
            "指数英文名称Index Name(Eng)": ["CSI 500", "CSI 500"],
            "成份券代码Constituent Code": [750, 2230],
            "成份券名称Constituent Name": ["宁德时代", "科大讯飞"],
            "成份券英文名称Constituent Name(Eng)": ["Contemporary Amperex Technology", "iFlytek"],
            "交易所Exchange": ["深圳证券交易所", "深圳证券交易所"],
            "交易所英文名称Exchange(Eng)": [
                "Shenzhen Stock Exchange",
                "Shenzhen Stock Exchange",
            ],
            "权重(%)weight": [0.8, 0.6],
        }
    )

    weights = normalize_csi300_weights(raw)
    assert weights["index_code"].tolist() == ["000905", "000905"]
    assert weights["symbol"].tolist() == ["SZ000750", "SZ002230"]


def test_write_csi500_outputs(tmp_path: Path) -> None:
    weights = pd.DataFrame(
        {
            "asof_date": ["2026-02-27", "2026-02-27"],
            "index_code": ["000905", "000905"],
            "index_name": ["中证500", "中证500"],
            "index_name_eng": ["CSI 500", "CSI 500"],
            "symbol": ["SZ000750", "SZ002230"],
            "constituent_code": ["000750", "002230"],
            "constituent_name": ["宁德时代", "科大讯飞"],
            "constituent_name_eng": ["Contemporary Amperex Technology", "iFlytek"],
            "exchange": ["深圳证券交易所", "深圳证券交易所"],
            "exchange_eng": ["Shenzhen Stock Exchange", "Shenzhen Stock Exchange"],
            "weight_pct": [0.8, 0.6],
            "source": ["official", "official"],
            "detail_page": ["detail", "detail"],
        }
    )

    paths = write_csi500_outputs(
        weights=weights,
        out=str(tmp_path / "current" / "csi500_symbols.txt"),
        weights_out=str(tmp_path / "current" / "csi500_weights.csv"),
        snapshot_dir=str(tmp_path / "snapshots"),
        weights_snapshot_dir=str(tmp_path / "weights"),
    )

    assert (tmp_path / "current" / "csi500_symbols.txt").read_text(encoding="utf-8") == (
        "SZ000750\nSZ002230\n"
    )
    metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert metadata["asof_date"] == "2026-02-27"
    assert metadata["symbol_count"] == 2

    snapshot = pd.read_csv(tmp_path / "snapshots" / "csi500_membership_2026-02-27.csv")
    assert snapshot["symbol"].tolist() == ["SZ000750", "SZ002230"]

    weights_snapshot = pd.read_csv(tmp_path / "weights" / "csi500_weights_2026-02-27.csv")
    assert weights_snapshot["weight_pct"].tolist() == [0.8, 0.6]
