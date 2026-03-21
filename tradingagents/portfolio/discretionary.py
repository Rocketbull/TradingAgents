from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from tradingagents.dataflows.market_data_store import (
    download_history,
    save_history_parquet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _coerce_repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


@dataclass
class DiscretionaryHolding:
    shares: float
    avg_cost: float


@dataclass
class DiscretionaryActivity:
    action: str
    symbol: str
    shares: float
    price: float
    cash_before: float
    cash_after: float
    notional: float
    cost: float
    trade_time_utc: str
    trade_date: str
    note: str = ""
    trade_id: str | None = None


@dataclass
class DiscretionaryPortfolio:
    name: str = "default"
    cash: float = 100_000.0
    holdings: Dict[str, DiscretionaryHolding] = field(default_factory=dict)
    activities: List[DiscretionaryActivity] = field(default_factory=list)
    transaction_cost_bps: float = 5.0
    slippage_bps: float = 0.0
    data_root: Path = Path("data/market")
    state_path: Path = Path("eval_results/discretionary_portfolio/default_portfolio.json")

    def __post_init__(self) -> None:
        self.data_root = _coerce_repo_path(self.data_root)
        self.state_path = _coerce_repo_path(self.state_path)

    @classmethod
    def load(
        cls,
        state_path: str | Path = "eval_results/discretionary_portfolio/default_portfolio.json",
        name: str = "default",
        initial_cash: float = 100_000.0,
        transaction_cost_bps: float = 5.0,
        slippage_bps: float = 0.0,
        data_root: str | Path = "data/market",
    ) -> "DiscretionaryPortfolio":
        path = _coerce_repo_path(state_path)
        if not path.exists():
            return cls(
                name=name,
                cash=float(initial_cash),
                transaction_cost_bps=float(transaction_cost_bps),
                slippage_bps=float(slippage_bps),
                data_root=_coerce_repo_path(data_root),
                state_path=path,
            )

        payload = json.loads(path.read_text(encoding="utf-8"))
        holdings = {
            symbol: DiscretionaryHolding(
                shares=float(vals["shares"]),
                avg_cost=float(vals["avg_cost"]),
            )
            for symbol, vals in payload.get("holdings", {}).items()
        }
        activities = [
            DiscretionaryActivity(
                action=str(row.get("action", "")),
                symbol=str(row.get("symbol", "")).upper(),
                shares=float(row.get("shares", 0.0)),
                price=float(row.get("price", 0.0)),
                cash_before=float(row.get("cash_before", 0.0)),
                cash_after=float(row.get("cash_after", 0.0)),
                notional=float(row.get("notional", 0.0)),
                cost=float(row.get("cost", 0.0)),
                trade_time_utc=str(row.get("trade_time_utc", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))),
                trade_date=str(row.get("trade_date", datetime.utcnow().strftime("%Y-%m-%d"))),
                note=str(row.get("note", "")),
                trade_id=str(row.get("trade_id", "")) if row.get("trade_id") else None,
            )
            for row in payload.get("activities", [])
        ]

        return cls(
            name=str(payload.get("name", name)),
            cash=float(payload.get("cash", initial_cash)),
            holdings=holdings,
            activities=activities,
            transaction_cost_bps=float(payload.get("transaction_cost_bps", transaction_cost_bps)),
            slippage_bps=float(payload.get("slippage_bps", slippage_bps)),
            data_root=_coerce_repo_path(payload.get("data_root", str(data_root))),
            state_path=path,
        )

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": self.name,
            "cash": self.cash,
            "transaction_cost_bps": self.transaction_cost_bps,
            "slippage_bps": self.slippage_bps,
            "data_root": str(self.data_root),
            "generated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "holdings": {
                symbol: asdict(holding) for symbol, holding in sorted(self.holdings.items())
            },
            "activities": [
                {
                    **asdict(activity),
                    "symbol": activity.symbol,
                }
                for activity in self.activities
            ],
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return str(symbol or "").strip().upper()

    @staticmethod
    def _parse_history_name(path: Path) -> tuple[datetime, datetime] | None:
        stem = path.stem
        if not stem.startswith("history_"):
            return None
        parts = stem.split("_")
        if len(parts) != 3:
            return None
        try:
            start = datetime.strptime(parts[1], "%Y-%m-%d")
            end = datetime.strptime(parts[2], "%Y-%m-%d")
            return start, end
        except ValueError:
            return None

    def _price_files(self, symbol: str) -> List[Path]:
        symbol_dir = self.data_root / self._normalize_symbol(symbol)
        if not symbol_dir.exists():
            return []
        return sorted(symbol_dir.glob("history_*.parquet"))

    def _has_five_year_history(self, symbol: str, as_of: datetime) -> bool:
        as_of = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        min_start = as_of - timedelta(days=365 * 5)
        for path in self._price_files(symbol):
            parsed = self._parse_history_name(path)
            if parsed is None:
                continue
            start, end = parsed
            if start <= min_start <= end and end >= as_of:
                return True
            if start <= min_start and end >= as_of:
                return True
        return False

    def ensure_symbol_history(self, symbol: str, as_of: Optional[datetime] = None, overwrite: bool = False) -> Path:
        symbol = self._normalize_symbol(symbol)
        if not symbol:
            raise ValueError("symbol is required")

        as_of = as_of or datetime.utcnow()
        as_of = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        if not self._has_five_year_history(symbol, as_of) or overwrite:
            start_date = (as_of - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
            end_date_exclusive = (as_of + timedelta(days=1)).strftime("%Y-%m-%d")
            df = download_history(symbol, start_date, end_date_exclusive)
            path = save_history_parquet(
                df=df,
                symbol=symbol,
                start_date=start_date,
                end_date=as_of.strftime("%Y-%m-%d"),
                root_dir=str(self.data_root),
            )
            return path

        candidates = self._price_files(symbol)
        if not candidates:
            raise FileNotFoundError(f"No history file found for {symbol}")
        return candidates[-1]

    def add_ticker(self, symbol: str, as_of: Optional[datetime] = None) -> None:
        symbol = self._normalize_symbol(symbol)
        if not symbol:
            raise ValueError("symbol is required")
        self.ensure_symbol_history(symbol, as_of=as_of)
        self.holdings.setdefault(symbol, DiscretionaryHolding(shares=0.0, avg_cost=0.0))

    def _pick_price_file(self, symbol: str, as_of: datetime) -> Path:
        symbol = self._normalize_symbol(symbol)
        target = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        files = self._price_files(symbol)
        if not files:
            raise FileNotFoundError(f"No history data for symbol '{symbol}'")

        parsed_by_date = []
        fallback = []
        for path in files:
            parsed = self._parse_history_name(path)
            if parsed is None:
                continue
            start, end = parsed
            parsed_by_date.append((start, end, path))
            if end < target:
                fallback.append((end, path))
            elif start <= target <= end:
                return path

        if fallback:
            fallback.sort(key=lambda x: x[0], reverse=True)
            return fallback[0][1]

        if parsed_by_date:
            parsed_by_date.sort(key=lambda x: x[1], reverse=True)
            return parsed_by_date[0][2]
        raise FileNotFoundError(f"No history file for '{symbol}' after parsing filename metadata")

    def _latest_eod_price(self, symbol: str) -> float:
        symbol = self._normalize_symbol(symbol)
        files = self._price_files(symbol)
        if not files:
            raise FileNotFoundError(f"No history data for symbol '{symbol}'")

        # Parquet files are stored using end-date in filename; the last file usually
        # corresponds to the freshest market snapshot.
        latest_file = sorted(files)[-1]
        df = pd.read_parquet(latest_file)
        if "Date" not in df.columns:
            raise ValueError(f"History file for {symbol} missing Date column")
        price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        if price_col not in df.columns:
            raise ValueError(f"History file for {symbol} missing {price_col}")

        series = (
            df[["Date", price_col]]
            .assign(Date=lambda x: pd.to_datetime(x["Date"]))
            .set_index("Date")[price_col]
            .sort_index()
        )
        if series.empty:
            raise ValueError(f"History file for {symbol} is empty")
        return float(series.iloc[-1])

    def _price_at(self, symbol: str, as_of: datetime) -> float:
        symbol = self._normalize_symbol(symbol)
        self.add_ticker(symbol, as_of=as_of)
        path = self._pick_price_file(symbol, as_of)
        df = pd.read_parquet(path)
        if "Date" not in df.columns:
            raise ValueError(f"History file for {symbol} missing Date column")
        price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
        if price_col not in df.columns:
            raise ValueError(f"History file for {symbol} missing {price_col}")

        df = (
            df[["Date", price_col]]
            .assign(Date=lambda x: pd.to_datetime(x["Date"]))
            .set_index("Date")[price_col]
            .sort_index()
        )
        now = pd.Timestamp(as_of)
        prior = df[df.index <= now]
        if prior.empty:
            raise ValueError(f"No prices for {symbol} on or before {as_of.date()}")
        return float(prior.iloc[-1])

    def _record_activity(
        self,
        action: str,
        symbol: str,
        shares: float,
        price: float,
        cash_before: float,
        cash_after: float,
        note: str = "",
    ) -> None:
        notional = shares * price
        fee = abs(notional) * (self.transaction_cost_bps + self.slippage_bps) / 10_000.0
        now = datetime.utcnow()
        self.activities.append(
            DiscretionaryActivity(
                action=action,
                symbol=self._normalize_symbol(symbol),
                shares=float(shares),
                price=float(price),
                cash_before=float(cash_before),
                cash_after=float(cash_after),
                notional=float(notional),
                cost=float(fee),
                trade_time_utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                trade_date=now.strftime("%Y-%m-%d"),
                note=note,
                trade_id=f"ACT-{int(now.timestamp() * 1000)}",
            )
        )

    def _buy_shares(
        self,
        symbol: str,
        shares: float,
        effective_price: float,
        note: str,
    ) -> None:
        cost = shares * effective_price
        fee = abs(cost) * (self.transaction_cost_bps + self.slippage_bps) / 10_000.0
        total = cost + fee
        if total > self.cash + 1e-12:
            raise ValueError("insufficient cash for buy")

        cash_before = self.cash
        self.cash -= total
        current = self.holdings.get(symbol, DiscretionaryHolding(shares=0.0, avg_cost=0.0))
        next_shares = current.shares + shares
        next_cost = ((current.shares * current.avg_cost) + (shares * effective_price)) / next_shares if next_shares > 0 else 0.0
        self.holdings[symbol] = DiscretionaryHolding(shares=float(next_shares), avg_cost=float(next_cost))

        self._record_activity(
            action="BUY",
            symbol=symbol,
            shares=float(shares),
            price=effective_price,
            cash_before=cash_before,
            cash_after=self.cash,
            note=note,
        )

    def _sell_shares(
        self,
        symbol: str,
        shares: float,
        effective_price: float,
        note: str,
    ) -> None:
        current = self.holdings.get(symbol)
        if current is None or current.shares <= 0:
            raise ValueError(f"no shares to sell for {symbol}")
        if shares > current.shares + 1e-12:
            raise ValueError(f"not enough shares for {symbol}")

        proceeds = shares * effective_price
        fee = abs(proceeds) * (self.transaction_cost_bps + self.slippage_bps) / 10_000.0
        net = proceeds - fee

        cash_before = self.cash
        self.cash += net
        remaining = current.shares - shares
        if remaining <= 0:
            self.holdings.pop(symbol, None)
        else:
            self.holdings[symbol] = DiscretionaryHolding(shares=float(remaining), avg_cost=float(current.avg_cost))

        self._record_activity(
            action="SELL",
            symbol=symbol,
            shares=float(-shares),
            price=effective_price,
            cash_before=cash_before,
            cash_after=self.cash,
            note=note,
        )

    def buy(
        self,
        symbol: str,
        target_weight: float,
        as_of: Optional[datetime] = None,
        note: str = "manual buy",
    ) -> float:
        if target_weight < 0 or target_weight > 1:
            raise ValueError("target_weight must be in [0, 1]")
        as_of = as_of or datetime.utcnow()
        symbol = self._normalize_symbol(symbol)
        self.add_ticker(symbol, as_of=as_of)
        effective_price = self._latest_eod_price(symbol)
        portfolio_value, frame = self.current_valuation(as_of=as_of)
        current_shares = float(frame.loc[symbol, "shares"]) if symbol in frame.index else 0.0
        target_shares = (portfolio_value * target_weight) / effective_price
        shares = target_shares - current_shares
        if shares <= 1e-12:
            raise ValueError("target_weight must be above current position weight")
        self._buy_shares(
            symbol=symbol,
            shares=shares,
            effective_price=effective_price,
            note=note,
        )
        return effective_price

    def sell(
        self,
        symbol: str,
        target_weight: float,
        as_of: Optional[datetime] = None,
        note: str = "manual sell",
    ) -> float:
        if target_weight < 0 or target_weight > 1:
            raise ValueError("target_weight must be in [0, 1]")
        as_of = as_of or datetime.utcnow()
        symbol = self._normalize_symbol(symbol)
        current = self.holdings.get(symbol)
        if current is None or current.shares <= 0:
            raise ValueError(f"no shares to sell for {symbol}")

        effective_price = self._latest_eod_price(symbol)
        portfolio_value, frame = self.current_valuation(as_of=as_of)
        current_shares = float(frame.loc[symbol, "shares"]) if symbol in frame.index else current.shares
        target_shares = (portfolio_value * target_weight) / effective_price
        shares = current_shares - target_shares
        if shares <= 1e-12:
            raise ValueError("target_weight must be below current position weight")
        self._sell_shares(
            symbol=symbol,
            shares=shares,
            effective_price=effective_price,
            note=note,
        )
        return effective_price

    def current_valuation(self, as_of: Optional[datetime] = None) -> tuple[float, pd.DataFrame]:
        as_of = as_of or datetime.utcnow()
        rows = []
        total = self.cash
        for symbol, holding in self.holdings.items():
            price = self._price_at(symbol, as_of)
            mv = holding.shares * price
            total += mv
            rows.append(
                {
                    "symbol": symbol,
                    "shares": float(holding.shares),
                    "avg_cost": float(holding.avg_cost),
                    "last_price": float(price),
                    "market_value": float(mv),
                }
            )
        frame = pd.DataFrame(rows).set_index("symbol") if rows else pd.DataFrame(columns=["symbol", "shares", "avg_cost", "last_price", "market_value"]).set_index("symbol")
        return float(total), frame

    def rebalance(self, target_weights: Dict[str, float], as_of: Optional[datetime] = None) -> list[DiscretionaryActivity]:
        as_of = as_of or datetime.utcnow()
        active = {self._normalize_symbol(s): float(w) for s, w in target_weights.items() if self._normalize_symbol(s)}
        if not active:
            raise ValueError("target_weights is empty")

        # Ensure all target symbols are ready in local cache (5y window auto-refresh)
        for symbol in active.keys():
            self.add_ticker(symbol, as_of=as_of)

        total_weight = sum(max(0.0, w) for w in active.values())
        if total_weight <= 0:
            raise ValueError("target_weights must have positive exposure")
        active = {s: w / total_weight for s, w in active.items() if max(0.0, w) > 0}

        before_activities = len(self.activities)
        portfolio_value, current_frame = self.current_valuation(as_of=as_of)

        target_values = {s: float(w) * portfolio_value for s, w in active.items()}
        current_prices = {
            s: self._price_at(s, as_of)
            for s in set(current_frame.index).union(active.keys())
        }
        current_shares = {
            s: float(current_frame.loc[s, "shares"]) if s in current_frame.index else 0.0
            for s in active.keys() | set(current_frame.index)
        }

        rebalance_deltas = {}
        for symbol, target_value in target_values.items():
            price = current_prices[symbol]
            if price <= 0:
                continue
            target_shares = target_value / price
            delta = target_shares - current_shares.get(symbol, 0.0)
            if abs(delta) > 1e-8:
                rebalance_deltas[symbol] = delta

        # Defer execution so sells free cash before buys when both are required.
        for symbol, delta in sorted(rebalance_deltas.items(), key=lambda item: item[1]):
            price = current_prices[symbol]
            if delta < 0:
                self._sell_shares(
                    symbol=symbol,
                    shares=-delta,
                    effective_price=price,
                    note="rebalance",
                )

        for symbol, delta in sorted(rebalance_deltas.items(), key=lambda item: item[1]):
            price = current_prices[symbol]
            if delta > 0:
                self._buy_shares(
                    symbol=symbol,
                    shares=delta,
                    effective_price=price,
                    note="rebalance",
                )

        # Clear non-target zero/near-zero positions
        for symbol in list(self.holdings.keys()):
            if symbol in active:
                continue
            if abs(self.holdings[symbol].shares) < 1e-12:
                self.holdings.pop(symbol, None)

        return self.activities[before_activities:]

    def holdings_frame(self, as_of: Optional[datetime] = None) -> pd.DataFrame:
        as_of = as_of or datetime.utcnow()
        total, frame = self.current_valuation(as_of=as_of)
        if frame.empty:
            return pd.DataFrame(columns=["symbol", "shares", "avg_cost", "last_price", "market_value", "weight"])
        frame = frame.copy()
        frame["weight"] = frame["market_value"] / total if total > 0 else 0.0
        frame = frame.sort_values("symbol")
        return frame.reset_index()

    def activity_log(self) -> pd.DataFrame:
        if not self.activities:
            return pd.DataFrame(
                columns=[
                    "trade_time_utc",
                    "trade_date",
                    "action",
                    "symbol",
                    "shares",
                    "price",
                    "notional",
                    "cost",
                    "cash_before",
                    "cash_after",
                    "note",
                    "trade_id",
                ]
            )
        return pd.DataFrame([asdict(row) for row in self.activities])
