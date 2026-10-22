"""QAContext: lazy, cached access to every dataset a check may need.

    ctx.raw("fact")        file data, all-string (as delivered)
    ctx.typed("fact")      file data, parsed/normalised
    ctx.db_raw("dm")       DB table, stringified
    ctx.db_typed("dm")     DB table, parsed/normalised
    ctx.expected_dm()      target data mart recomputed independently from the FILES
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from src.config import Settings
from src.file_reader_core import LoadedFile, load_file
from src.logger import get_logger
from src.normalizer import normalize_frame, to_str
from src.results import PrerequisiteError

log = get_logger("context")


class QAContext:
    def __init__(self, settings: Settings, db_enabled: bool = True):
        self.s = settings
        self.db_enabled = db_enabled
        self._files: Dict[str, LoadedFile] = {}
        self._raw: Dict[str, pd.DataFrame] = {}
        self._typed: Dict[str, tuple] = {}
        self._db_raw: Dict[str, pd.DataFrame] = {}
        self._db_typed: Dict[str, tuple] = {}
        self._expected_dm: Optional[pd.DataFrame] = None
        self._db = None
        self._db_error = ""

    # ---------------- test helper (unit tests / synthetic data) ----------
    @classmethod
    def from_frames(cls, settings: Settings, files: Dict[str, pd.DataFrame] | None = None,
                    db: Dict[str, pd.DataFrame] | None = None) -> "QAContext":
        ctx = cls(settings, db_enabled=bool(db))
        ctx._synthetic = True
        for k, df in (files or {}).items():
            ctx._raw[k] = to_str_frame(df)
            ctx._files[k] = LoadedFile(key=k, label=k, path=None, df=ctx._raw[k], encoding="utf-8")
        for k, df in (db or {}).items():
            ctx._db_raw[k] = to_str_frame(df)
        return ctx

    # ---------------- config helpers -------------------------------------
    @property
    def rules(self) -> dict:
        return self.s.rules

    @property
    def thresholds(self) -> dict:
        return self.s.rules["thresholds"]

    # ---------------- schema helpers -------------------------------------
    def schema(self, key: str) -> dict:
        return self.s.schema[key]

    def pk(self, key: str) -> str:
        return self.s.schema[key]["primary_key"]

    # ---------------- files ----------------------------------------------
    def file(self, key: str) -> LoadedFile:
        if key not in self._files:
            lf = load_file(key, self.s.cfg["files"][key], self.s.path("input_dir"))
            log.info("Loaded %s: %s rows, encoding=%s%s", lf.label, 0 if lf.df is None else len(lf.df),
                     lf.encoding, f" ERROR={lf.error}" if lf.error else "")
            self._files[key] = lf
        return self._files[key]

    def raw(self, key: str) -> pd.DataFrame:
        if key in self._raw:
            return self._raw[key]
        lf = self.file(key)
        if lf.error or lf.df is None:
            raise PrerequisiteError(f"{lf.label} file unavailable: {lf.error}")
        self._raw[key] = lf.df
        return lf.df

    def typed(self, key: str) -> pd.DataFrame:
        return self._typed_pair(key)[0]

    def invalid(self, key: str) -> pd.DataFrame:
        return self._typed_pair(key)[1]

    def _typed_pair(self, key: str):
        if key not in self._typed:
            self._typed[key] = normalize_frame(self.raw(key), self.schema(key), self.s.execution)
        return self._typed[key]

    # ---------------- database -------------------------------------------
    @property
    def db(self):
        if not self.db_enabled:
            raise PrerequisiteError("Database checks disabled (--skip-db)")
        if self._db is None and self._db_raw and not self._db_error and self.s is not None and getattr(self, "_synthetic", False):
            return None                      # synthetic frames injected by unit tests
        if self._db is None and not self._db_error:
            from src.database import Database
            try:
                self._db = Database(self.s).connect()
            except Exception as exc:  # noqa: BLE001
                self._db_error = f"{type(exc).__name__}: {exc}"
                log.error("Database connection failed: %s", self._db_error)
        if self._db is None:
            if self._db_raw:      # synthetic frames supplied
                return None
            raise PrerequisiteError(f"Database unavailable: {self._db_error}")
        return self._db

    def db_raw(self, key: str) -> pd.DataFrame:
        if key not in self._db_raw:
            db = self.db
            self._db_raw[key] = db.read_table(self.s.tables[key])
            log.info("Read table %s: %s rows", self.s.tables[key], len(self._db_raw[key]))
        return self._db_raw[key]

    def db_typed(self, key: str) -> pd.DataFrame:
        return self._db_typed_pair(key)[0]

    def db_invalid(self, key: str) -> pd.DataFrame:
        return self._db_typed_pair(key)[1]

    def _db_typed_pair(self, key: str):
        if key not in self._db_typed:
            self._db_typed[key] = normalize_frame(self.db_raw(key), self.schema(key), self.s.execution)
        return self._db_typed[key]

    # ---------------- derived ----------------------------------------------
    def expected_dm(self) -> pd.DataFrame:
        if self._expected_dm is None:
            from src.reconciliation import build_expected_dm
            self._expected_dm = build_expected_dm(self.typed("fact"), self.typed("dist"), self.typed("cust"))
        return self._expected_dm

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


def to_str_frame(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({c: to_str(df[c]) for c in df.columns}, index=df.index)
