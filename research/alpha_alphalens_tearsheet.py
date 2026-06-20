from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from alphalens import tears
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "alphalens-reloaded is required. Install with: "
        "conda run -n activepm python -m pip install alphalens-reloaded"
    ) from exc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render Alphalens tearsheets from saved factor_data.parquet.")
    p.add_argument(
        "--factor-data",
        required=True,
        help="Path to factor_data.parquet from research/alpha_alphalens_adapter.py.",
    )
    p.add_argument("--out-dir", default=None, help="Optional directory to save PNG figures.")
    p.add_argument("--prefix", default="alphalens", help="Filename prefix for saved figures.")
    p.add_argument("--dpi", type=int, default=140)
    p.add_argument("--long-short", action="store_true", default=True)
    p.add_argument("--no-long-short", action="store_true", help="Disable long-short tearsheet mode.")
    p.add_argument("--group-neutral", action="store_true")
    p.add_argument("--by-group", action="store_true")
    p.add_argument("--turnover-periods", default="5,20", help="Comma-separated periods for turnover tearsheet.")
    p.add_argument(
        "--show",
        action="store_true",
        help="Show figures interactively. Without this flag, plots are saved only when --out-dir is set.",
    )
    return p.parse_args()


def parse_periods(raw: str) -> list[int]:
    vals: list[int] = []
    for token in str(raw).split(","):
        t = token.strip()
        if not t:
            continue
        v = int(t)
        if v < 1:
            raise ValueError("turnover periods must be >= 1")
        vals.append(v)
    return sorted(set(vals)) or [5, 20]


def save_open_figures(out_dir: Path, prefix: str, dpi: int) -> list[Path]:
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    fig_nums = list(plt.get_fignums())
    for i, fig_num in enumerate(fig_nums, start=1):
        fig = plt.figure(fig_num)
        path = out_dir / f"{prefix}_{i:02d}.png"
        fig.savefig(path, dpi=int(dpi), bbox_inches="tight")
        paths.append(path)
    return paths


def main() -> None:
    args = parse_args()
    factor_path = Path(args.factor_data)
    if not factor_path.exists():
        raise FileNotFoundError(f"factor_data not found: {factor_path}")

    # Use non-interactive backend by default for script usage.
    if not bool(args.show):
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    factor_data = pd.read_parquet(factor_path)
    if not isinstance(factor_data.index, pd.MultiIndex) or factor_data.index.nlevels != 2:
        raise ValueError("factor_data must be a MultiIndex dataframe with (date, asset) index.")

    long_short = bool(args.long_short) and not bool(args.no_long_short)
    turnover_periods = parse_periods(args.turnover_periods)

    tears.create_returns_tear_sheet(
        factor_data=factor_data,
        long_short=long_short,
        group_neutral=bool(args.group_neutral),
        by_group=bool(args.by_group),
    )
    tears.create_information_tear_sheet(
        factor_data=factor_data,
        group_neutral=bool(args.group_neutral),
        by_group=bool(args.by_group),
    )
    try:
        tears.create_turnover_tear_sheet(
            factor_data=factor_data,
            turnover_periods=turnover_periods,
        )
    except Exception as exc:
        # Some alphalens/pandas combinations are brittle for turnover plotting.
        print(f"[warn] turnover tearsheet skipped: {exc}")

    saved: list[Path] = []
    if args.out_dir:
        saved = save_open_figures(Path(args.out_dir), prefix=str(args.prefix), dpi=int(args.dpi))
        print(f"[ok] saved {len(saved)} figure(s) under {args.out_dir}")
        for p in saved:
            print(f"[ok] {p}")

    if bool(args.show):
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
