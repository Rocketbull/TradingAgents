from __future__ import annotations

from datetime import date, datetime
from typing import Any
import json

import pandas as pd
import requests

from .market_data_store import parquet_path_for_symbol, save_history_parquet


REQUEST_TIMEOUT_SECONDS = 15
SUPPORTED_FREQUENCIES = {"1d", "1w", "1M", "1m", "5m", "15m", "30m", "60m"}


def normalize_symbol(symbol: str) -> str:
    """Normalize A-share symbols to a stable SHxxxxxx/SZxxxxxx form."""
    raw = str(symbol or "").strip()
    if not raw:
        raise ValueError("symbol is required")

    upper = raw.upper()
    if len(upper) == 8 and upper[:2] in {"SH", "SZ"} and upper[2:].isdigit():
        return upper

    if upper.endswith(".XSHG") or upper.endswith(".SH"):
        code = upper.split(".", 1)[0]
        if code.isdigit() and len(code) == 6:
            return f"SH{code}"

    if upper.endswith(".XSHE") or upper.endswith(".SZ"):
        code = upper.split(".", 1)[0]
        if code.isdigit() and len(code) == 6:
            return f"SZ{code}"

    if upper.startswith(("SH", "SZ")) and len(upper) == 8 and upper[2:].isdigit():
        return upper

    if upper.isdigit() and len(upper) == 6:
        # Default bare numeric symbols to Shanghai because this module is
        # intended for SH market workflows unless the caller specifies otherwise.
        return f"SH{upper}"

    raise ValueError(
        "Unsupported A-share symbol format. Use forms like SH600519, "
        "600519.SH, 600519.XSHG, SZ000001, or 000001.XSHE."
    )


def vendor_symbol(symbol: str) -> str:
    canonical = normalize_symbol(symbol)
    return canonical[:2].lower() + canonical[2:]


def _request_json(url: str) -> Any:
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return json.loads(response.content)


def get_price_day_tx(
    code: str,
    end_date: str | date | datetime = "",
    count: int = 10,
    frequency: str = "1d",
) -> pd.DataFrame:
    """Fetch daily/weekly/monthly history from Tencent."""
    unit_map = {"1d": "day", "1w": "week", "1M": "month"}
    if frequency not in unit_map:
        raise ValueError(f"Unsupported daily frequency: {frequency}")

    if end_date:
        if isinstance(end_date, (date, datetime)):
            end_date_str = end_date.strftime("%Y-%m-%d")
        else:
            end_date_str = str(end_date).split(" ")[0]
    else:
        end_date_str = ""

    today = datetime.now().strftime("%Y-%m-%d")
    if end_date_str == today:
        end_date_str = ""

    unit = unit_map[frequency]
    url = (
        "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?param={code},{unit},,{end_date_str},{count},qfq"
    )
    payload = _request_json(url)
    stock_payload = payload["data"][code]
    payload_key = f"qfq{unit}"
    rows = stock_payload[payload_key] if payload_key in stock_payload else stock_payload[unit]

    df = pd.DataFrame(rows, columns=["time", "open", "close", "high", "low", "volume"])
    df["time"] = pd.to_datetime(df["time"])
    for column in ["open", "close", "high", "low", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.set_index("time").sort_index()


def get_price_min_tx(
    code: str,
    end_date: str | date | datetime | None = None,
    count: int = 10,
    frequency: str = "1m",
) -> pd.DataFrame:
    """Fetch intraday history from Tencent."""
    interval = frequency[:-1]
    ts = int(interval) if interval.isdigit() else 1
    url = f"http://ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},m{ts},,{count}"
    payload = _request_json(url)
    rows = payload["data"][code][f"m{ts}"]

    df = pd.DataFrame(
        rows,
        columns=["time", "open", "close", "high", "low", "volume", "n1", "n2"],
    )[["time", "open", "close", "high", "low", "volume"]]
    df["time"] = pd.to_datetime(df["time"])
    for column in ["open", "close", "high", "low", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    quote = payload["data"][code].get("qt", {}).get(code, [])
    if len(quote) > 3:
        df.loc[df.index[-1], "close"] = float(quote[3])
    return df.set_index("time").sort_index()


def get_price_sina(
    code: str,
    end_date: str | date | datetime = "",
    count: int = 10,
    frequency: str = "60m",
) -> pd.DataFrame:
    """Fetch history from Sina for daily/weekly/monthly and intraday bars."""
    normalized_frequency = (
        frequency.replace("1d", "240m").replace("1w", "1200m").replace("1M", "7200m")
    )
    interval = normalized_frequency[:-1]
    ts = int(interval) if interval.isdigit() else 1
    requested_count = count

    end_ts: pd.Timestamp | None = None
    if end_date and normalized_frequency in {"240m", "1200m", "7200m"}:
        end_ts = pd.Timestamp(end_date)
        unit_days = {"240m": 1, "1200m": 4, "7200m": 29}[normalized_frequency]
        count += max((datetime.now() - end_ts.to_pydatetime()).days // unit_days, 0)

    url = (
        "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={code}&scale={ts}&ma=5&datalen={count}"
    )
    rows = _request_json(url)
    df = pd.DataFrame(rows, columns=["day", "open", "high", "low", "close", "volume"])
    df["day"] = pd.to_datetime(df["day"])
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.set_index("day").sort_index()

    if end_ts is not None:
        return df[df.index <= end_ts].tail(requested_count)
    return df


def get_price(
    code: str,
    end_date: str | date | datetime = "",
    count: int = 10,
    frequency: str = "1d",
    fields: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch history from the preferred A-share endpoint with fallback."""
    del fields  # Kept for compatibility with the original Ashare signature.

    if frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(f"Unsupported frequency: {frequency}")

    xcode = vendor_symbol(code)
    if frequency in {"1d", "1w", "1M"}:
        try:
            return get_price_sina(xcode, end_date=end_date, count=count, frequency=frequency)
        except Exception:
            return get_price_day_tx(xcode, end_date=end_date, count=count, frequency=frequency)

    if frequency == "1m":
        return get_price_min_tx(xcode, end_date=end_date, count=count, frequency=frequency)

    try:
        return get_price_sina(xcode, end_date=end_date, count=count, frequency=frequency)
    except Exception:
        return get_price_min_tx(xcode, end_date=end_date, count=count, frequency=frequency)


def _estimate_fetch_count(start_date: str, end_date: str, frequency: str) -> int:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    if start_dt > end_dt:
        raise ValueError("start_date must be <= end_date")

    calendar_days = (end_dt - start_dt).days + 1
    if frequency == "1d":
        return max(calendar_days * 2, 120)
    if frequency == "1w":
        return max((calendar_days // 7) + 16, 52)
    if frequency == "1M":
        months = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month) + 1
        return max(months + 6, 24)

    interval_minutes = int(frequency[:-1])
    trading_bars_per_day = max(240 // interval_minutes, 1)
    return max(calendar_days * trading_bars_per_day * 2, 240)


def _to_history_schema(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.reset_index().rename(
        columns={
            "time": "Date",
            "day": "Date",
            "index": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Unexpected Ashare schema. Missing columns: {missing}")

    history = frame[required].copy()
    history["Date"] = pd.to_datetime(history["Date"])
    history = history.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        history[column] = pd.to_numeric(history[column], errors="coerce")
    history["Adj Close"] = history["Close"]
    return history[
        ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    ].reset_index(drop=True)


def download_history(
    symbol: str,
    start_date: str,
    end_date: str,
    frequency: str = "1d",
) -> pd.DataFrame:
    """Download A-share OHLCV history in the repo's standard parquet schema."""
    canonical_symbol = normalize_symbol(symbol)
    count = _estimate_fetch_count(start_date, end_date, frequency)
    raw = get_price(canonical_symbol, end_date=end_date, count=count, frequency=frequency)
    history = _to_history_schema(raw)

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    history = history[(history["Date"] >= start_ts) & (history["Date"] < end_ts)]
    if history.empty:
        raise ValueError(
            f"No Ashare data returned for symbol '{canonical_symbol}' in range "
            f"{start_date}..{end_date}"
        )
    return history.reset_index(drop=True)


def download_history_to_parquet(
    symbol: str,
    start_date: str,
    end_date: str,
    root_dir: str = "data/market",
    frequency: str = "1d",
    overwrite: bool = False,
):
    """Download A-share history and persist it using the repo parquet layout."""
    canonical_symbol = normalize_symbol(symbol)
    target = parquet_path_for_symbol(
        symbol=canonical_symbol,
        start_date=start_date,
        end_date=end_date,
        root_dir=root_dir,
    )
    if target.exists() and not overwrite:
        return target

    df = download_history(canonical_symbol, start_date, end_date, frequency=frequency)
    return save_history_parquet(
        df=df,
        symbol=canonical_symbol,
        start_date=start_date,
        end_date=end_date,
        root_dir=root_dir,
        source="ashare",
    )
