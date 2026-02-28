from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ResearchRunManager:
    out_dir: Path
    params: dict[str, Any]
    run_tag: str | None = None
    tag_prefix: str = "run"

    def resolved_run_tag(self) -> str:
        if self.run_tag:
            return str(self.run_tag)
        return self.deterministic_tag(self.params, prefix=self.tag_prefix)

    def run_dir(self) -> Path:
        d = self.out_dir / self.resolved_run_tag()
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def deterministic_tag(params: dict[str, Any], prefix: str = "run") -> str:
        payload = json.dumps(params, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
        start = str(params.get("start_date", "na"))
        end = str(params.get("end_date", "na"))
        return f"{prefix}_{start}_{end}_{digest}"

    @staticmethod
    def git_head() -> str | None:
        try:
            out = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            return out.decode("utf-8").strip()
        except Exception:
            return None

    def write_params(self, extra: dict[str, Any] | None = None) -> Path:
        payload = dict(self.params)
        if extra:
            payload.update(extra)
        payload["run_tag"] = self.resolved_run_tag()
        payload["generated_at_utc"] = datetime.now(tz=timezone.utc).isoformat()
        path = self.run_dir() / "params.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_manifest(
        self,
        artifacts: dict[str, str | None],
        config_json: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        payload: dict[str, Any] = {
            "run_tag": self.resolved_run_tag(),
            "created_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "command": " ".join(sys.argv),
            "python_version": platform.python_version(),
            "git_head": self.git_head(),
            "config_json": config_json,
            "artifacts": artifacts,
        }
        if extra:
            payload.update(extra)
        path = self.run_dir() / "manifest.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
