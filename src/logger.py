"""Structured logging: console + rotating execution.log."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"


def setup_logging(logs_dir: Path, level: int = logging.INFO) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("qa")
    root.setLevel(level)
    if not root.handlers:
        fh = RotatingFileHandler(logs_dir / "execution.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT))
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(levelname)-7s | %(message)s"))
        root.addHandler(fh)
        root.addHandler(ch)
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"qa.{name}")
