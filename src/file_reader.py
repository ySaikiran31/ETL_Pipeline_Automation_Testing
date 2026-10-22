"""File Reader module: loaders (re-exported) + structural checks for the three source files.

Modules covered: FIL-001 .. FIL-012
"""
from __future__ import annotations

import pandas as pd

from src.file_reader_core import LoadedFile, detect_encoding, load_file, resolve_path  # noqa: F401
from src.registry import qa_check
from src.results import Outcome

LABELS = {"dist": "Distributor Sales (JSON)", "fact": "Fact Sales (CSV)", "cust": "Customer Master (TXT/CSV)"}
MODULE = "File Structure Validation"


def _register(key: str, n_exists: int, n_cols: int, n_struct: int, n_rows: int):
    area = {"dist": "Source data", "fact": "Source data", "cust": "Customer Master"}[key]

    @qa_check(f"FIL-{n_exists:03d}", suite="file_validation", module=MODULE, category="File availability",
              title=f"{LABELS[key]}: file exists, is non-empty and readable", severity="Critical",
              dataset=LABELS[key], defect_area="Environment/configuration")
    def _exists(ctx, key=key):
        """File must exist, be non-empty, have a detectable encoding and parse without error."""
        lf = ctx.file(key)
        if lf.error:
            return Outcome.from_bool(False, "", lf.error, {"file": str(lf.path or ""), "failure_reason": lf.error})
        return Outcome.from_bool(True, f"{lf.path.name}: {lf.size_bytes:,} bytes, encoding={lf.encoding}, "
                                       f"{len(lf.df):,} records, {len(lf.df.columns)} columns", "")

    @qa_check(f"FIL-{n_cols:03d}", suite="file_validation", module=MODULE, category="Structure",
              title=f"{LABELS[key]}: column names match the expected layout", severity="Critical",
              dataset=LABELS[key], defect_area=area, requires=[key])
    def _columns(ctx, key=key):
        """No missing and no unexpected columns versus the DDL-derived expected layout."""
        expected = [c["name"] for c in ctx.schema(key)["columns"]]
        actual = list(ctx.raw(key).columns)
        rows = [{"column": c, "failure_reason": "Expected column missing from file"} for c in expected if c not in actual]
        rows += [{"column": c, "failure_reason": "Unexpected column in file"} for c in actual if c not in expected]
        order_ok = [c for c in actual if c in expected] == [c for c in expected if c in actual]
        total = len(expected)
        if rows:
            return Outcome(total=total, failed=pd.DataFrame(rows), message=f"{len(rows)} column difference(s)")
        return Outcome(total=total, message=f"All {total} expected columns present" + ("" if order_ok else " (column ORDER differs - informational)"))

    @qa_check(f"FIL-{n_struct:03d}", suite="file_validation", module=MODULE, category="Structure",
              title=f"{LABELS[key]}: delimiter / record structure is well-formed", severity="High",
              dataset=LABELS[key], defect_area=area, requires=[key])
    def _structure(ctx, key=key):
        """Correct delimiter, every record has the full set of fields, no malformed records."""
        lf = ctx.file(key)
        rows = list(lf.malformed)
        spec = ctx.s.cfg["files"][key]
        if spec["format"] == "delimited" and lf.detected_delimiter and lf.detected_delimiter != spec["delimiter"]:
            rows.insert(0, {"reason": f"Header delimiter looks like '{lf.detected_delimiter}', config expects '{spec['delimiter']}'"})
        total = len(lf.df) + len(lf.malformed)
        if rows:
            return Outcome(total=total, failed=pd.DataFrame(rows), message=f"{len(rows):,} malformed record(s)/structure issue(s)")
        return Outcome(total=total, message=f"All {total:,} records well-formed (format={spec['format']}, delimiter='{spec.get('delimiter', 'n/a')}')")

    @qa_check(f"FIL-{n_rows:03d}", suite="file_validation", module=MODULE, category="Completeness",
              title=f"{LABELS[key]}: record count is non-zero and as expected", severity="High",
              dataset=LABELS[key], defect_area=area, requires=[key])
    def _rows(ctx, key=key):
        """Record count > 0 and equal to the configured expected count (if one is configured)."""
        n = len(ctx.raw(key))
        expected = ctx.s.execution.get("expected_row_counts", {}).get(key)
        if n == 0:
            return Outcome.from_bool(False, "", "File contains zero data records")
        if expected is not None and n != expected:
            return Outcome.from_bool(False, "", f"Record count {n:,} != expected {expected:,}",
                                     {"actual": n, "expected": expected})
        return Outcome.from_bool(True, f"{n:,} records" + (f" (expected {expected:,})" if expected else ""), "")


_register("dist", 1, 4, 7, 10)
_register("fact", 2, 5, 8, 11)
_register("cust", 3, 6, 9, 12)
