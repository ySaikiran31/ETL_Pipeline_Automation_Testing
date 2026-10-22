"""Low-level, dependency-free file loading (encoding detection, delimited/JSON readers)."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pandas as pd

csv.field_size_limit(10_000_000)


@dataclass
class LoadedFile:
    key: str
    label: str
    path: Optional[Path]
    df: Optional[pd.DataFrame] = None
    encoding: str = ""
    size_bytes: int = 0
    detected_delimiter: str = ""
    malformed: List[dict] = field(default_factory=list)   # structural problems
    error: str = ""


def resolve_path(input_dir: Path, name: str) -> Optional[Path]:
    """Case-insensitive file lookup (lab loader fails on Linux because of case)."""
    exact = input_dir / name
    if exact.exists():
        return exact
    if input_dir.exists():
        for p in input_dir.iterdir():
            if p.name.lower() == name.lower():
                return p
    return None


def detect_encoding(path: Path) -> str:
    raw = path.read_bytes()[:65536]
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    sample = raw[:400]
    if len(sample) >= 20:
        if sum(1 for i in range(1, len(sample), 2) if sample[i] == 0) >= 10:
            return "utf-16-le"
        if sum(1 for i in range(0, len(sample), 2) if sample[i] == 0) >= 10:
            return "utf-16-be"
    try:
        path.read_bytes().decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def detect_delimiter(header_line: str) -> str:
    counts = {d: header_line.count(d) for d in [",", "|", "\t", ";"]}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ""


def read_delimited(path: Path, delimiter: str, encoding: str) -> tuple[pd.DataFrame, List[dict], str]:
    """Read a delimited file as all-string. Rows with wrong field count are collected, not loaded."""
    rows, malformed = [], []
    with open(path, "r", encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        header = [h.strip() for h in next(reader)]
        header_line_delim = detect_delimiter(",".join(header) if delimiter == "," else delimiter.join(header))
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                malformed.append({"line_number": reader.line_num, "fields_found": len(row),
                                  "fields_expected": len(header), "raw": delimiter.join(row)[:200]})
                continue
            rows.append(row)
    df = pd.DataFrame(rows, columns=header, dtype=object)
    return df, malformed, header_line_delim


def read_json_records(path: Path, encoding: str) -> tuple[pd.DataFrame, List[dict]]:
    with open(path, "r", encoding=encoding) as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("JSON root must be an array of objects")
    good, malformed, expected_keys = [], [], None
    for idx, rec in enumerate(data):
        if isinstance(rec, dict):
            expected_keys = expected_keys or set(rec)
            if set(rec) != expected_keys:
                malformed.append({"record_index": idx, "reason": "inconsistent keys",
                                  "raw": str(sorted(set(rec) ^ expected_keys))[:200]})
            good.append({k: ("" if v is None else str(v)) for k, v in rec.items()})
        else:
            malformed.append({"record_index": idx, "reason": "not a JSON object", "raw": str(rec)[:200]})
    return pd.DataFrame(good).astype(object), malformed


def load_file(key: str, spec: dict, input_dir: Path) -> LoadedFile:
    lf = LoadedFile(key=key, label=spec["label"], path=resolve_path(input_dir, spec["name"]))
    if lf.path is None:
        lf.error = f"File not found: {input_dir / spec['name']}"
        return lf
    lf.size_bytes = lf.path.stat().st_size
    if lf.size_bytes == 0:
        lf.error = "File is empty (0 bytes)"
        return lf
    try:
        lf.encoding = detect_encoding(lf.path)
        if spec["format"] == "json":
            lf.df, lf.malformed = read_json_records(lf.path, lf.encoding)
            lf.detected_delimiter = "json"
        else:
            lf.df, lf.malformed, lf.detected_delimiter = read_delimited(lf.path, spec["delimiter"], lf.encoding)
        lf.df.columns = [str(c).strip() for c in lf.df.columns]
    except Exception as exc:  # noqa: BLE001 - surfaced as FAIL by FIL-002
        lf.error = f"{type(exc).__name__}: {exc}"
    return lf
