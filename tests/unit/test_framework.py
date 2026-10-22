"""Framework self-tests (positive + negative).

Positive : clean synthetic data must produce NO false alarms.
Negative : each injected defect must be caught by the intended validation.
No source files or MySQL needed:  pytest tests/unit
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.context import QAContext
from src.config import load_settings
from src.reconciliation import build_expected_dm, compare_frames
from src.registry import CHECKS, load_all_checks
from src.results import FAIL, PASS, SKIPPED
from src.runner import run_check
from tests.unit.factory import dm_frame_from_expected, make_clean, unit_settings

pytestmark = pytest.mark.unit
load_all_checks()


@pytest.fixture(scope="module")
def settings():
    return unit_settings(load_settings())


def _ctx(settings, mutate=None, files=("dist", "fact", "cust")):
    dist, fact, cust = make_clean()
    frames = {"dist": dist, "fact": fact, "cust": cust}
    if mutate:
        mutate(frames)
    return QAContext.from_frames(settings, files=frames)


def _status(ctx, test_id):
    return run_check(CHECKS[test_id], ctx).status


# ----------------------------------------------------------------- positive
FILE_ONLY = sorted(t for t, s in CHECKS.items() if not any(r.startswith("db") for r in s.requires) and t not in ("DB-001", "FIL-001", "FIL-002", "FIL-003", "FIL-007", "FIL-008", "FIL-009"))


@pytest.mark.parametrize("test_id", FILE_ONLY)
def test_clean_data_has_no_false_alarms(settings, test_id):
    ctx = _ctx(settings)
    res = run_check(CHECKS[test_id], ctx)
    assert res.status == PASS, f"{test_id}: {res.status} {res.message}"
    ctx.close()


def test_clean_expected_data_mart_passes_all_dm_and_recon_checks(settings):
    dist, fact, cust = make_clean()
    ctx = QAContext.from_frames(settings, files={"dist": dist, "fact": fact, "cust": cust})
    ctx.db_enabled, ctx._synthetic = True, True
    ctx._db_raw["dm"] = dm_frame_from_expected(ctx)
    for test_id in [t for t, s in CHECKS.items() if s.suite in ("datamart_validation", "reconciliation") and all(r in ("dist", "fact", "cust", "db:dm") for r in s.requires) and s.requires]:
        res = run_check(CHECKS[test_id], ctx)
        assert res.status == PASS, f"{test_id}: {res.status} {res.message}"


# ----------------------------------------------------------------- negative: source files
def _m(fn):
    return fn


NEGATIVE = [
    ("DST-002", "duplicate txn id in distributor", lambda f: f["dist"].__setitem__("distributor_txn_id", f["dist"]["distributor_txn_id"].where(f["dist"].index != 5, f["dist"].at[4, "distributor_txn_id"]))),
    ("DST-001", "blank gross_amount", lambda f: f["dist"].__setitem__("gross_amount", f["dist"]["gross_amount"].where(f["dist"].index != 3, ""))),
    ("DST-008", "invalid status", lambda f: f["dist"].__setitem__("status", f["dist"]["status"].where(f["dist"].index != 3, "PENDING"))),
    ("DST-007", "commission > gross", lambda f: f["dist"].__setitem__("commission_amount", f["dist"]["commission_amount"].where(f["dist"].index != 3, "99999999.00"))),
    ("DST-013", "bad PAN", lambda f: f["dist"].__setitem__("customer_pan", f["dist"]["customer_pan"].where(f["dist"].index != 3, "12345"))),
    ("DST-005", "unparseable date", lambda f: f["dist"].__setitem__("sale_date", f["dist"]["sale_date"].where(f["dist"].index != 3, "31/31/2026"))),
    ("FAC-003", "duplicate txn id in fact", lambda f: f["fact"].__setitem__("distributor_txn_id", f["fact"]["distributor_txn_id"].where(f["fact"].index != 5, f["fact"].at[4, "distributor_txn_id"]))),
    ("FAC-006", "negative tax", lambda f: f["fact"].__setitem__("tax_amount", f["fact"]["tax_amount"].where(f["fact"].index != 3, "-1.00"))),
    ("FIL-005", "missing column", lambda f: f.__setitem__("fact", f["fact"].drop(columns=["net_amount"]))),
    ("CUS-004", "duplicate customer_id", lambda f: f["cust"].__setitem__("customer_id", f["cust"]["customer_id"].where(f["cust"].index != 5, f["cust"].at[4, "customer_id"]))),
    ("CUS-007", "invalid gender", lambda f: f["cust"].__setitem__("gender", f["cust"]["gender"].where(f["cust"].index != 3, "X"))),
    ("REF-001", "orphan customer reference", lambda f: f["dist"].__setitem__("customer_id", f["dist"]["customer_id"].where(f["dist"].index != 3, "CUST999999"))),
    ("REF-002", "fact customer_key not in master", lambda f: f["fact"].__setitem__("customer_key", f["fact"]["customer_key"].where(f["fact"].index != 3, "777777"))),
    ("REF-005", "PAN mismatch dist vs master", lambda f: f["cust"].__setitem__("customer_pan", f["cust"]["customer_pan"].where(f["cust"].index != 3, "ZZZZZ9999Z"))),
    ("CAL-001", "net_amount wrong", lambda f: f["fact"].__setitem__("net_amount", f["fact"]["net_amount"].where(f["fact"].index != 3, "1.00"))),
    ("CAL-002", "commission_pct wrong", lambda f: f["fact"].__setitem__("commission_pct", f["fact"]["commission_pct"].where(f["fact"].index != 3, "9.999"))),
    ("CAL-003", "units x nav wrong", lambda f: f["fact"].__setitem__("units_allocated", f["fact"]["units_allocated"].where(f["fact"].index != 4, "1.0000"))),
    ("CAL-006", "high-value flag wrong", lambda f: f["fact"].__setitem__("is_high_value_flag", f["fact"]["is_high_value_flag"].where(f["fact"].index != 3, "Y"))),
    ("PRD-001", "unknown product prefix", lambda f: f["dist"].__setitem__("product_code", f["dist"]["product_code"].where(f["dist"].index != 3, "XYZ_001"))),
    ("PRD-002", "type/family mismatch", lambda f: f["dist"].__setitem__("product_type_raw", f["dist"]["product_type_raw"].where(f["dist"].index != 4, "ULIP"))),
    ("PRD-003", "family field population", lambda f: f["fact"].__setitem__("premium_amount", f["fact"]["premium_amount"].where(f["fact"].index != 4, "10.00"))),
    ("MAP-002", "region blank", lambda f: f["dist"].__setitem__("region_code", f["dist"]["region_code"].where(f["dist"].index != 3, ""))),
    ("REC-010", "txn missing in fact", lambda f: f.__setitem__("fact", f["fact"].drop(index=[3]))),
    ("REC-011", "gross differs dist vs fact", lambda f: f["fact"].__setitem__("gross_amount", f["fact"]["gross_amount"].where(f["fact"].index != 3, "1.00"))),
    ("BR-002", "date key drift", lambda f: f["fact"].__setitem__("sale_date_key", f["fact"]["sale_date_key"].where(f["fact"].index != 3, "20250101"))),
]


@pytest.mark.parametrize("test_id,desc,mutation", NEGATIVE, ids=[f"{t}-{d}" for t, d, _ in NEGATIVE])
def test_injected_defect_is_detected(settings, test_id, desc, mutation):
    ctx = _ctx(settings, mutation)
    res = run_check(CHECKS[test_id], ctx)
    assert res.status == FAIL, f"{test_id} failed to detect '{desc}': {res.status} {res.message}"
    assert res.failed_records >= 1


# ----------------------------------------------------------------- negative: target data mart
def _dm_ctx(settings):
    dist, fact, cust = make_clean()
    ctx = QAContext.from_frames(settings, files={"dist": dist, "fact": fact, "cust": cust})
    ctx.db_enabled, ctx._synthetic = True, True
    ctx._db_raw["dm"] = dm_frame_from_expected(ctx)
    return ctx


DM_NEGATIVE = [
    ("DM-002", "REJECTED row leaked into mart", lambda d: d.__setitem__("status", d["status"].where(d.index != 2, "REJECTED"))),
    ("DM-003", "wrong product_family", lambda d: d.__setitem__("product_family", d["product_family"].where(d.index != 2, "INS" if d.at[2, "product_family"] == "MF" else "MF"))),
    ("DM-004", "commission > gross", lambda d: d.__setitem__("commission_amount", d["commission_amount"].where(d.index != 2, "99999999.00"))),
    ("DM-009", "dm_sk gap", lambda d: d.__setitem__("dm_sk", d["dm_sk"].where(d.index != 2, "9999"))),
    ("DM-010", "ins flag wrong", lambda d: d.__setitem__("is_ins_txn_flag", d["is_ins_txn_flag"].where(d.index != 2, "N" if d.at[2, "is_ins_txn_flag"] == "Y" else "Y"))),
    ("DM-012", "customer_id blank", lambda d: d.__setitem__("customer_id", d["customer_id"].where(d.index != 2, ""))),
    ("REC-020", "row dropped from mart", None),
    ("REC-022", "extra row in mart", None),
    ("REC-023", "gross differs from fact", lambda d: d.__setitem__("gross_amount", d["gross_amount"].where(d.index != 2, "1.00"))),
    ("REC-024", "product_code differs", lambda d: d.__setitem__("product_code", d["product_code"].where(d.index != 2, "MF_ZZZ_999"))),
    ("REC-026", "gross total differs", lambda d: d.__setitem__("gross_amount", d["gross_amount"].where(d.index != 2, "1.00"))),
    ("CAL-007", "net wrong in mart", lambda d: d.__setitem__("net_amount", d["net_amount"].where(d.index != 2, "1.00"))),
]


@pytest.mark.parametrize("test_id,desc,mutation", DM_NEGATIVE, ids=[f"{t}-{d}" for t, d, _ in DM_NEGATIVE])
def test_injected_data_mart_defect_is_detected(settings, test_id, desc, mutation):
    ctx = _dm_ctx(settings)
    d = ctx._db_raw["dm"]
    if test_id == "REC-020":
        d = d.drop(index=[2]).reset_index(drop=True)
    elif test_id == "REC-022":
        extra = d.iloc[[0]].copy()
        extra["distributor_txn_id"] = "DSC-EXTRA-1"
        d = pd.concat([d, extra], ignore_index=True)
    else:
        mutation(d)
    ctx._db_raw["dm"] = d
    ctx._db_typed.clear()
    res = run_check(CHECKS[test_id], ctx)
    assert res.status == FAIL, f"{test_id} failed to detect '{desc}': {res.status} {res.message}"


# ----------------------------------------------------------------- engine
def test_compare_frames_detects_missing_extra_and_mismatch():
    a = pd.DataFrame({"k": [1, 2, 3], "v": [10.0, 20.0, 30.0], "s": ["a", "b", None]})
    b = pd.DataFrame({"k": [2, 3, 4], "v": [20.0, 31.0, 40.0], "s": ["b", None, "d"]})
    r = compare_frames(a, b, "k", ["v", "s"])
    assert r["missing"]["k"].tolist() == [1]
    assert r["extra"]["k"].tolist() == [4]
    assert r["mismatches"][["k", "column"]].values.tolist() == [[3, "v"]]       # None == None must NOT mismatch
    assert r["compared_keys"] == 2 and r["matched_keys"] == 1


def test_compare_frames_ignores_duplicate_keys_but_reports_them():
    a = pd.DataFrame({"k": [1, 1], "v": [1, 1]})
    b = pd.DataFrame({"k": [1], "v": [1]})
    assert compare_frames(a, b, "k", ["v"])["dup_source"] == 1


def test_expected_data_mart_business_logic(settings):
    ctx = _ctx(settings)
    dm = ctx.expected_dm()
    approved = (ctx.typed("fact")["status"] == "APPROVED").sum()
    assert len(dm) == approved                                  # REJECTED excluded
    assert set(dm["product_family"]) <= {"MF", "INS"}
    assert dm["dm_sk"].tolist() == list(range(1, len(dm) + 1))
    assert dm["customer_age"].dropna().between(40, 50).all()    # born 1980, sale 2026 -> 45/46


def test_date_parsing_uses_configured_formats(settings):
    from src.normalizer import parse_column
    col = {"name": "d", "type": "date"}
    parsed, bad = parse_column(pd.Series(["1/31/2026", "2026-02-03", "13/45/2026", ""]), col, settings.execution)
    assert parsed.notna().tolist() == [True, True, False, False]
    assert bad.tolist() == [False, False, True, False]          # blank is NULL, not "invalid"


def test_missing_input_file_fails_file_check_and_skips_dependents(settings, tmp_path):
    import copy
    s = copy.deepcopy(settings)
    s.cfg["paths"]["input_dir"] = str(tmp_path)
    ctx = QAContext(s, db_enabled=False)
    assert _status(ctx, "FIL-001") == FAIL
    assert _status(ctx, "DST-001") == SKIPPED


def test_registry_ids_unique_and_documented():
    assert len(CHECKS) >= 100
    for spec in CHECKS.values():
        assert spec.title and spec.module and spec.severity in ("Critical", "High", "Medium", "Low")
