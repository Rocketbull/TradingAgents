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
    universe_snapshot_dir: Optional[Path] = None

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
        asof_date: Optional[str] = None,
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
        elif source == "sp500_snapshot":
            if self.universe_snapshot_dir is None:
                raise FileNotFoundError("universe_snapshot_dir is not configured")
            snapshot_path = self._pick_snapshot_file(self.universe_snapshot_dir, asof_date)
            if snapshot_path is None:
                raise FileNotFoundError(
                    f"No SP500 snapshot found under {self.universe_snapshot_dir} for asof_date={asof_date}"
                )
            symbols = self._read_snapshot_symbols(snapshot_path)[:portfolio_universe_size]
        else:
            symbols = [fallback_symbol.upper()]

        if benchmark not in symbols:
            symbols = [benchmark] + symbols
        return list(dict.fromkeys(symbols))

    @staticmethod
    def _parse_snapshot_date(path: Path) -> Optional[datetime]:
        stem = path.stem  # sp500_membership_YYYY-MM-DD
        prefix = "sp500_membership_"
        if not stem.startswith(prefix):
            return None
        tail = stem[len(prefix) :]
        try:
            return datetime.strptime(tail, "%Y-%m-%d")
        except ValueError:
            return None

    def _pick_snapshot_file(self, root: Path, asof_date: Optional[str]) -> Optional[Path]:
        if not root.exists():
            return None
        asof = datetime.strptime(asof_date, "%Y-%m-%d") if asof_date else datetime.utcnow()
        candidates: list[tuple[datetime, Path]] = []
        for path in root.glob("sp500_membership_*.csv"):
            dt = self._parse_snapshot_date(path)
            if dt is None:
                continue
            if dt <= asof:
                candidates.append((dt, path))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    @staticmethod
    def _read_snapshot_symbols(path: Path) -> list[str]:
        df = pd.read_csv(path)
        if df.empty:
            return []
        if "symbol" in df.columns:
            raw = df["symbol"].astype(str).tolist()
        else:
            raw = df.iloc[:, 0].astype(str).tolist()
        symbols: list[str] = []
        seen: set[str] = set()
        for value in raw:
            symbol = str(value).strip().upper().replace(".", "-")
            if symbol and symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
        return symbols

    def load_close_matrix(
        self, symbols: Iterable[str], start_date: str, end_date: str
    ) -> pd.DataFrame:
        return self.load_field_matrix(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            field_candidates=["Adj Close", "Close"],
        )

    def load_volume_matrix(
        self, symbols: Iterable[str], start_date: str, end_date: str
    ) -> pd.DataFrame:
        return self.load_field_matrix(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            field_candidates=["Volume"],
        )

    def load_symbol_series(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        field_candidates: list[str] | None = None,
    ) -> pd.Series:
        field_candidates = field_candidates or ["Adj Close", "Close"]
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        symbol_up = str(symbol).upper()
        symbol_dir = self.data_root / symbol_up
        if not symbol_dir.exists():
            raise FileNotFoundError(f"Symbol directory not found for {symbol_up}: {symbol_dir}")

        path = self._pick_parquet(symbol_dir, start_dt, end_dt)
        if path is None:
            raise FileNotFoundError(
                f"No parquet data found for {symbol_up} covering {start_date}..{end_date}"
            )

        df = pd.read_parquet(path)
        if "Date" not in df.columns:
            raise ValueError(f"Unexpected schema for {symbol_up}: missing Date column")
        col = next((c for c in field_candidates if c in df.columns), None)
        if col is None:
            raise ValueError(f"None of requested fields found for {symbol_up}: {field_candidates}")

        s = (
            df[["Date", col]]
            .rename(columns={col: symbol_up})
            .assign(Date=lambda x: pd.to_datetime(x["Date"]))
            .set_index("Date")[symbol_up]
            .sort_index()
        )
        s = s[(s.index >= pd.Timestamp(start_dt)) & (s.index <= pd.Timestamp(end_dt))]
        if s.empty:
            raise ValueError(f"No rows for {symbol_up} in range {start_date}..{end_date}")
        return s

    def load_field_matrix(
        self,
        symbols: Iterable[str],
        start_date: str,
        end_date: str,
        field_candidates: list[str],
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
            col = next((c for c in field_candidates if c in df.columns), None)
            if col is None:
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
        closes = closes.sort_index().ffill().dropna(axis=1, how="all")
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
