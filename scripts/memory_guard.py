#!/usr/bin/env python3
"""Lightweight checks for project memory hygiene."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_MEMORY_FILES = [
    "INDEX.md",
    "PROJECT.md",
    "ENGINEERING_PRINCIPLES.md",
    "ARCHITECTURE.md",
    "WORKFLOWS.md",
    "DECISIONS.md",
    "REFLECTIONS.md",
    "PITFALLS.md",
    "FEEDBACK.md",
    "WORKLOG.md",
]

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check project memory hygiene.")
    parser.add_argument("--memory-dir", default="memory", help="Memory directory.")
    parser.add_argument("--agents", default="AGENTS.md", help="Agent guide path.")
    parser.add_argument(
        "--max-agents-lines",
        type=int,
        default=120,
        help="Maximum preferred AGENTS.md length.",
    )
    parser.add_argument(
        "--max-index-lines",
        type=int,
        default=80,
        help="Maximum preferred memory/INDEX.md length.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def line_count(path: Path) -> int:
    return len(read_text(path).splitlines())


def check_heading(path: Path, errors: list[str]) -> None:
    text = read_text(path)
    if not text.startswith("# "):
        errors.append(f"{path} must start with a top-level Markdown heading")


def check_secrets(path: Path, errors: list[str]) -> None:
    text = read_text(path)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"{path} appears to contain a secret-like value")
            return


def main() -> int:
    args = parse_args()
    memory_dir = Path(args.memory_dir)
    agents_path = Path(args.agents)
    errors: list[str] = []

    if not agents_path.exists():
        errors.append(f"missing {agents_path}")
    else:
        check_heading(agents_path, errors)
        if line_count(agents_path) > args.max_agents_lines:
            errors.append(f"{agents_path} is too long; keep operating guidance compact")
        if "memory/INDEX.md" not in read_text(agents_path):
            errors.append(f"{agents_path} should point agents to memory/INDEX.md")

    if not memory_dir.is_dir():
        errors.append(f"missing {memory_dir}/")
    else:
        for filename in REQUIRED_MEMORY_FILES:
            path = memory_dir / filename
            if not path.exists():
                errors.append(f"missing {path}")
                continue
            check_heading(path, errors)
            check_secrets(path, errors)

        index_path = memory_dir / "INDEX.md"
        if index_path.exists() and line_count(index_path) > args.max_index_lines:
            errors.append(f"{index_path} is too long; keep the index as a map")

    if errors:
        print("Memory guard failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Memory guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
