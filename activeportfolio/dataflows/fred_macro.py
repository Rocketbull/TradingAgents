from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pandas as pd
import requests


FRED_API_BASE = "https://api.stlouisfed.org/fred"
REQUEST_TIMEOUT = 30


class FredMacroConfigurationError(ValueError):
    """Raised when FRED access is required but no API key is available."""


def _read_dotenv_value(var_names: list[str], dotenv_path: Path | None = None) -> str | None:
    path = dotenv_path or Path.cwd() / ".env"
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in var_names:
            continue
        value = value.strip().strip("'").strip('"')
        if value:
            return value
    return None


def get_fred_api_key() -> str:
    for name in ("FRED_API_KEY", "FRED_API"):
        value = os.getenv(name)
        if value:
            return value
    value = _read_dotenv_value(["FRED_API_KEY", "FRED_API"])
    if value:
        return value
    raise FredMacroConfigurationError(
        "FRED API key not found. Set FRED_API_KEY or FRED_API in the environment or .env."
    )


def _request(path: str, params: dict[str, str]) -> dict:
    response = requests.get(
        f"{FRED_API_BASE}/{path}",
        params={**params, "api_key": get_fred_api_key(), "file_type": "json"},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 400:
        try:
            message = response.json().get("error_message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"FRED request failed: {message}")
    response.raise_for_status()
    return response.json()


def _normalize_series_id(series_id: str) -> str:
    out = str(series_id).strip().upper()
    if not out:
        raise ValueError("series_id must be non-empty")
    return out


def parquet_path_for_series(
    series_id: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/macro/fred",
) -> Path:
    series = _normalize_series_id(series_id)
    return Path(root_dir) / series / f"history_{start_date}_{end_date}.parquet"


def _parse_history_name(path: Path) -> tuple[datetime, datetime] | None:
    stem = path.stem
    if not stem.startswith("history_"):
        return None
    parts = stem.split("_")
    if len(parts) != 3:
        return None
    try:
        return (
            datetime.strptime(parts[1], "%Y-%m-%d"),
            datetime.strptime(parts[2], "%Y-%m-%d"),
        )
    except ValueError:
        return None


def save_series_parquet(
    df: pd.DataFrame,
    series_id: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/macro/fred",
    title: str | None = None,
    frequency: str | None = None,
    units: str | None = None,
) -> Path:
    path = parquet_path_for_series(series_id, start_date, end_date, root_dir=root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    metadata = {
        "series_id": _normalize_series_id(series_id),
        "title": title or _normalize_series_id(series_id),
        "frequency": frequency,
        "units": units,
        "start_date": start_date,
        "end_date": end_date,
        "rows": int(df.shape[0]),
        "columns": list(df.columns),
        "saved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "fred",
    }
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path


def find_series_parquet(
    series_id: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/macro/fred",
) -> Path:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    series = _normalize_series_id(series_id)
    series_dir = Path(root_dir) / series
    if not series_dir.exists():
        raise FileNotFoundError(f"Series directory not found for {series}: {series_dir}")

    candidates: list[tuple[int, datetime, datetime, Path]] = []
    for path in series_dir.glob("history_*.parquet"):
        parsed = _parse_history_name(path)
        if parsed is None:
            continue
        file_start, file_end = parsed
        covers_range = 1 if (file_start <= start_dt and file_end >= end_dt) else 0
        candidates.append((covers_range, file_end, file_start, path))

    if not candidates:
        raise FileNotFoundError(f"No parquet history found for FRED series {series} in {series_dir}")

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return candidates[0][3]


def load_series_window(
    series_id: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/macro/fred",
) -> pd.DataFrame:
    path = find_series_parquet(series_id, start_date, end_date, root_dir=root_dir)
    df = pd.read_parquet(path)
    if "Date" not in df.columns or "Value" not in df.columns:
        raise ValueError(f"Unexpected schema for FRED series {_normalize_series_id(series_id)}")
    result = df.copy()
    result["Date"] = pd.to_datetime(result["Date"])
    result["Value"] = pd.to_numeric(result["Value"], errors="coerce")
    result = result[(result["Date"] >= pd.Timestamp(start_date)) & (result["Date"] <= pd.Timestamp(end_date))]
    result = result.dropna(subset=["Value"]).sort_values("Date").reset_index(drop=True)
    if result.empty:
        raise ValueError(
            f"No rows for FRED series {_normalize_series_id(series_id)} in range {start_date}..{end_date}"
        )
    return result


def download_series(
    series_id: str,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, dict[str, str | None]]:
    series = _normalize_series_id(series_id)
    meta = _request("series", {"series_id": series}).get("seriess") or []
    if not meta:
        raise ValueError(f"FRED series '{series}' not found")
    info = meta[0]
    observations = _request(
        "series/observations",
        {
            "series_id": series,
            "observation_start": start_date,
            "observation_end": end_date,
            "sort_order": "asc",
        },
    ).get("observations", [])
    rows = [
        {"Date": o["date"], "Value": float(o["value"])}
        for o in observations
        if o.get("value") not in (None, "", ".")
    ]
    if not rows:
        raise ValueError(f"No FRED observations returned for '{series}' in {start_date}..{end_date}")
    df = pd.DataFrame(rows)
    meta_out = {
        "title": info.get("title"),
        "frequency": info.get("frequency_short") or info.get("frequency"),
        "units": info.get("units_short") or info.get("units"),
    }
    return df, meta_out


@dataclass
class FREDMacroStore:
    root_dir: str = "data/macro/fred"
    auto_download: bool = True

    def load_series_window(self, series_id: str, start_date: str, end_date: str) -> pd.Series:
        try:
            df = load_series_window(
                series_id=series_id,
                start_date=start_date,
                end_date=end_date,
                root_dir=self.root_dir,
            )
        except (FileNotFoundError, ValueError):
            if not self.auto_download:
                raise
            df, meta = download_series(series_id=series_id, start_date=start_date, end_date=end_date)
            save_series_parquet(
                df=df,
                series_id=series_id,
                start_date=start_date,
                end_date=end_date,
                root_dir=self.root_dir,
                title=meta.get("title"),
                frequency=meta.get("frequency"),
                units=meta.get("units"),
            )
            df = load_series_window(
                series_id=series_id,
                start_date=start_date,
                end_date=end_date,
                root_dir=self.root_dir,
            )

        series = (
            df.assign(Date=lambda x: pd.to_datetime(x["Date"]))
            .set_index("Date")["Value"]
            .sort_index()
        )
        series.name = _normalize_series_id(series_id)
        return series

    def warm_series(self, series_ids: list[str], end_date: str, lookback_days: int) -> list[Path]:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=int(lookback_days))).strftime("%Y-%m-%d")
        paths: list[Path] = []
        for series_id in series_ids:
            df, meta = download_series(series_id=series_id, start_date=start_date, end_date=end_date)
            path = save_series_parquet(
                df=df,
                series_id=series_id,
                start_date=start_date,
                end_date=end_date,
                root_dir=self.root_dir,
                title=meta.get("title"),
                frequency=meta.get("frequency"),
                units=meta.get("units"),
            )
            paths.append(path)
        return paths
