from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


@dataclass
class LocalParquetDataLoader:
    """Load close prices from local market parquet files."""

    data_root: Path
    symbol_file: Optional[Path] = None

    @staticmethod
    def _parse_history_name(path: Path) -> Optional[tuple[datetime, datetime]]:
        stem = path.stem
        # history_YYYY-MM-DD_YYYY-MM-DD.parquet
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

    def load_symbols(
        self,
        universe_source: str,
        portfolio_universe: list[str],
        portfolio_universe_size: int,
        benchmark_symbol: str,
        fallback_symbol: str,
    ) -> list[str]:
        source = universe_source.lower()
        benchmark = benchmark_symbol.upper()

        if source == "config_list":
            symbols = [str(s).upper() for s in portfolio_universe if str(s).strip()]
        elif source == "sp500_file":
            if self.symbol_file is None or not self.symbol_file.exists():
                raise FileNotFoundError(f"Symbol file not found: {self.symbol_file}")
            symbols = [
                line.strip().upper()
                for line in self.symbol_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ][:portfolio_universe_size]
        else:
            symbols = [fallback_symbol.upper()]

        if benchmark not in symbols:
            symbols = [benchmark] + symbols
        return list(dict.fromkeys(symbols))

    def load_close_matrix(
        self, symbols: Iterable[str], start_date: str, end_date: str
    ) -> pd.DataFrame:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        per_symbol: dict[str, pd.Series] = {}
        for symbol in symbols:
            symbol_dir = self.data_root / symbol.upper()
            if not symbol_dir.exists():
                continue

            path = self._pick_parquet(symbol_dir, start_dt, end_dt)
            if path is None:
                continue

            df = pd.read_parquet(path)
            if "Date" not in df.columns:
                continue
            col = "Adj Close" if "Adj Close" in df.columns else "Close"
            if col not in df.columns:
                continue
            s = (
                df[["Date", col]]
                .rename(columns={col: symbol.upper()})
                .assign(Date=lambda x: pd.to_datetime(x["Date"]))
                .set_index("Date")[symbol.upper()]
                .sort_index()
            )
            s = s[(s.index >= pd.Timestamp(start_dt)) & (s.index <= pd.Timestamp(end_dt))]
            if not s.empty:
                per_symbol[symbol.upper()] = s

        if len(per_symbol) < 2:
            raise ValueError("Need at least 2 symbols with local parquet coverage.")

        closes = pd.concat(per_symbol.values(), axis=1, join="outer")
        closes.columns = list(per_symbol.keys())
        closes = closes.sort_index().ffill().dropna(axis=1, how="any")
        if closes.shape[1] < 2:
            raise ValueError("Insufficient aligned symbols after parquet load.")
        return closes

    def _pick_parquet(
        self, symbol_dir: Path, start_dt: datetime, end_dt: datetime
    ) -> Optional[Path]:
        candidates: list[tuple[int, datetime, datetime, Path]] = []
        for path in symbol_dir.glob("history_*.parquet"):
            parsed = self._parse_history_name(path)
            if parsed is None:
                continue
            file_start, file_end = parsed
            covers_range = 1 if (file_start <= start_dt and file_end >= end_dt) else 0
            candidates.append((covers_range, file_end, file_start, path))

        if not candidates:
            return None

        # Prefer files that fully cover the range, then most recent end/start dates.
        candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        return candidates[0][3]
