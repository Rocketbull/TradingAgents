#!/usr/bin/env python3
"""Append a short project-memory reflection."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path


DEFAULT_MEMORY_FILE = Path("memory/REFLECTIONS.md")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a short lesson to memory/REFLECTIONS.md."
    )
    parser.add_argument("note", help="The lesson or observation to remember.")
    parser.add_argument("--title", required=True, help="Short reflection title.")
    parser.add_argument(
        "--tags",
        default="",
        help="Optional comma-separated tags, for example: dataflow,tests.",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Reflection date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--file",
        default=str(DEFAULT_MEMORY_FILE),
        help="Memory file to append to. Defaults to memory/REFLECTIONS.md.",
    )
    return parser.parse_args()


def format_reflection(args: argparse.Namespace) -> str:
    tags = args.tags.strip()
    suffix = f" [{tags}]" if tags else ""
    return f"\n## {args.date}: {args.title}{suffix}\n{args.note.strip()}\n"


def main() -> int:
    args = parse_args()
    memory_file = Path(args.file)
    memory_file.parent.mkdir(parents=True, exist_ok=True)

    if not memory_file.exists():
        memory_file.write_text("# Reflections\n", encoding="utf-8")

    with memory_file.open("a", encoding="utf-8") as handle:
        handle.write(format_reflection(args))

    print(f"Appended reflection to {memory_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
