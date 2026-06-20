from __future__ import annotations

from pathlib import Path

import pandas as pd

from activeportfolio.dataflows.fred_macro import FREDMacroStore, get_fred_api_key


def test_get_fred_api_key_reads_fred_api_from_dotenv(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API", raising=False)
    (tmp_path / ".env").write_text("FRED_API=test-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert get_fred_api_key() == "test-key"


def test_fred_macro_store_uses_cached_parquet(tmp_path: Path):
    root = tmp_path / "macro"
    series_dir = root / "UNRATE"
    series_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "Date": ["2024-01-31", "2024-02-29", "2024-03-31"],
            "Value": [4.0, 4.1, 4.2],
        }
    ).to_parquet(series_dir / "history_2024-01-01_2024-12-31.parquet", index=False)

    store = FREDMacroStore(root_dir=str(root), auto_download=False)
    series = store.load_series_window("UNRATE", "2024-01-01", "2024-03-31")

    assert list(series.index.strftime("%Y-%m-%d")) == ["2024-01-31", "2024-02-29", "2024-03-31"]
    assert list(series.values) == [4.0, 4.1, 4.2]
