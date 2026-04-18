from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from activeportfolio.portfolio import DiscretionaryPortfolio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual discretionary portfolio tool with activity tracking."
    )
    parser.add_argument(
        "--state-path",
        default=str(REPO_ROOT / "eval_results" / "discretionary_portfolio" / "default_portfolio.json"),
        help="Path to persisted portfolio JSON state.",
    )
    parser.add_argument(
        "--data-root",
        default=str(REPO_ROOT / "data" / "market"),
        help="Market data root for parquet symbol history.",
    )
    parser.add_argument(
        "--name",
        default="default",
        help="Portfolio name used on first creation.",
    )
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=100_000.0,
        help="Initial cash when creating a new portfolio file.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=5.0,
        help="Transaction cost model (bps) for executed trades.",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=0.0,
        help="Slippage model (bps) for executed trades.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add ticker and bootstrap 5y history.")
    add_parser.add_argument("symbol", help="Ticker symbol (e.g. AAPL, SPY).")
    add_parser.add_argument(
        "--as-of",
        default=None,
        help="Optional YYYY-MM-DD timestamp for data bootstrap point.",
    )

    buy_parser = subparsers.add_parser("buy", help="Target-weight buy (set position to target weight).")
    buy_parser.add_argument("symbol", help="Ticker symbol.")
    buy_parser.add_argument("target_weight", type=float, help="Target portfolio weight after buy [0,1].")
    buy_parser.add_argument("--note", default="manual buy", help="Optional trade note.")

    sell_parser = subparsers.add_parser("sell", help="Target-weight sell (reduce position to target weight).")
    sell_parser.add_argument("symbol", help="Ticker symbol.")
    sell_parser.add_argument("target_weight", type=float, help="Target portfolio weight after sell [0,1].")
    sell_parser.add_argument("--note", default="manual sell", help="Optional trade note.")

    rebalance_parser = subparsers.add_parser(
        "rebalance",
        help="Rebalance to target weights (sum can be any positive total).",
    )
    rebalance_parser.add_argument(
        "--weight",
        action="append",
        required=True,
        help="Weight pair in SYMBOL:WEIGHT format. Repeatable (e.g. --weight AAPL:0.45).",
    )
    rebalance_parser.add_argument(
        "--as-of",
        default=None,
        help="Optional YYYY-MM-DD timestamp for rebalancing (defaults to now).",
    )

    show_parser = subparsers.add_parser("show", help="Display portfolio summary and open holdings.")
    show_parser.add_argument(
        "--as-of",
        default=None,
        help="Optional YYYY-MM-DD valuation date (defaults to now).",
    )

    log_parser = subparsers.add_parser("log", help="Display activity log.")
    log_parser.add_argument("--max", type=int, default=50, help="Maximum number of activity rows.")

    return parser.parse_args()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def parse_weights(raw: List[str]) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for token in raw:
        if ":" not in token:
            raise ValueError(f"weight token must be SYMBOL:WEIGHT, got '{token}'")
        symbol, value = token.split(":", 1)
        s = symbol.strip().upper()
        if not s:
            continue
        weights[s] = float(value.strip())
    return weights


def print_portfolio(state: DiscretionaryPortfolio, as_of: datetime | None) -> None:
    total, frame = state.current_valuation(as_of=as_of)
    print(f"name={state.name} total_valuation={total:.2f} cash={state.cash:.2f}")
    print("holdings:")
    if frame.empty:
        print("  (empty)")
    else:
        for row in frame.to_dict(orient="records"):
            print(
                f"  {row['symbol']}: shares={row['shares']:.6f} "
                f"avg_cost={row['avg_cost']:.4f} last_price={row['last_price']:.4f} "
                f"market_value={row['market_value']:.2f} weight={row['weight']:.4f}"
            )


def print_log(state: DiscretionaryPortfolio, limit: int) -> None:
    rows = state.activity_log().tail(limit).to_dict(orient="records")
    if not rows:
        print("(no activities)")
        return
    print("recent activities:")
    for row in rows:
        print(
            f"{row['trade_time_utc']} {row['action']} {row['symbol']} "
            f"shares={row['shares']:.6f} price={row['price']:.4f} "
            f"cash={row['cash_before']:.2f}->{row['cash_after']:.2f} note={row.get('note','')}"
        )


def main() -> None:
    args = parse_args()
    state = DiscretionaryPortfolio.load(
        state_path=args.state_path,
        name=args.name,
        initial_cash=args.initial_cash,
        transaction_cost_bps=args.transaction_cost_bps,
        slippage_bps=args.slippage_bps,
        data_root=args.data_root,
    )

    as_of = parse_datetime(args.__dict__.get("as_of"))

    if args.command == "add":
        state.add_ticker(args.symbol, as_of=as_of)
        state.save()
        print(f"[ok] ticker added: {args.symbol.upper()}")
    elif args.command == "buy":
        price = state.buy(
            symbol=args.symbol,
            target_weight=args.target_weight,
            as_of=as_of,
            note=args.note,
        )
        state.save()
        print(f"[ok] buy {args.symbol.upper()} target_weight={args.target_weight} price={price:.4f}")
    elif args.command == "sell":
        price = state.sell(
            symbol=args.symbol,
            target_weight=args.target_weight,
            as_of=as_of,
            note=args.note,
        )
        state.save()
        print(f"[ok] sell {args.symbol.upper()} target_weight={args.target_weight} price={price:.4f}")
    elif args.command == "rebalance":
        target_weights = parse_weights(args.weight)
        state.rebalance(target_weights=target_weights, as_of=as_of)
        state.save()
        print("[ok] rebalance completed")
        print_portfolio(state, as_of=as_of)
    elif args.command == "show":
        print_portfolio(state, as_of=as_of)
    elif args.command == "log":
        print_log(state, limit=args.max)


if __name__ == "__main__":
    main()
