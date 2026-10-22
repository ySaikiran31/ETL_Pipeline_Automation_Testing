"""Configuration loading (JSON files + environment-variable overrides).

Secrets (DB password) are NEVER stored in config files - environment only.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE). Does not override real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    cfg: Dict[str, Any]
    rules: Dict[str, Any]
    schema: Dict[str, Any]
    root: Path = PROJECT_ROOT
    db_password: str | None = field(default=None, repr=False)

    # ---- paths -------------------------------------------------------
    def path(self, key: str) -> Path:
        env = {"input_dir": "QA_INPUT_DIR", "reports_dir": "QA_REPORTS_DIR"}.get(key)
        value = os.getenv(env) if env else None
        p = Path(value or self.cfg["paths"][key])
        return p if p.is_absolute() else self.root / p

    # ---- database ----------------------------------------------------
    @property
    def db(self) -> Dict[str, Any]:
        d = dict(self.cfg["database"])
        d["host"] = os.getenv("QA_DB_HOST", d["host"])
        d["port"] = int(os.getenv("QA_DB_PORT", d["port"]))
        d["name"] = os.getenv("QA_DB_NAME", d["name"])
        d["user"] = os.getenv("QA_DB_USER", d["user"])
        d["password"] = self.db_password or os.getenv("QA_DB_PASSWORD") or os.getenv("P2_DB_PASSWORD")
        return d

    @property
    def tables(self) -> Dict[str, str]:
        return self.cfg["database"]["tables"]

    @property
    def execution(self) -> Dict[str, Any]:
        return self.cfg["execution"]

    @property
    def thresholds(self) -> Dict[str, Any]:
        return self.rules["thresholds"]


def load_settings(config_path: str | Path | None = None) -> Settings:
    _load_env_file(PROJECT_ROOT / ".env")
    cfg_path = Path(config_path or os.getenv("QA_CONFIG") or PROJECT_ROOT / "config" / "config.json")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    rules = json.loads((cfg_path.parent / "business_rules.json").read_text(encoding="utf-8"))
    schema = json.loads((cfg_path.parent / "schema.json").read_text(encoding="utf-8"))
    return Settings(cfg=cfg, rules=rules, schema=schema)
