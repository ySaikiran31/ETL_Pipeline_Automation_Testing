"""pytest wiring. Every validation in the registry becomes one parametrised test.

    pytest                      -> everything (needs files + MySQL)
    pytest --skip-db            -> file-only validations, DB tests SKIPPED
    pytest -m "not db"          -> same, deselected
    pytest -k REF-001           -> one validation
    pytest tests/unit           -> framework self-tests only (no data needed)
Reports are generated at the end of any run that executed validations.
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import pytest

from src.config import load_settings
from src.context import QAContext
from src.registry import CheckSpec
from src.report_generator import build_meta, write_reports
from src.results import ERROR, FAIL, PASS, SKIPPED
from src.runner import run_check


def pytest_addoption(parser):
    g = parser.getgroup("qa")
    g.addoption("--skip-db", action="store_true", help="skip every MySQL-dependent validation")
    g.addoption("--input-dir", default=None, help="folder with the three source files")
    g.addoption("--no-reports", action="store_true", help="do not write report files")


def pytest_configure(config):
    if config.getoption("--input-dir"):
        os.environ["QA_INPUT_DIR"] = config.getoption("--input-dir")
    config._qa = {"results": [], "specs": {}, "t0": time.perf_counter(), "started": datetime.now(), "ctx": None}


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def ctx(request, settings):
    c = QAContext(settings, db_enabled=not request.config.getoption("--skip-db"))
    request.config._qa["ctx"] = c
    yield c
    c.close()


@pytest.fixture
def qa_run(request, ctx, settings):
    """Run one registered validation, record it for reporting, translate status to pytest outcome."""
    state = request.config._qa

    def _run(spec: CheckSpec):
        result = run_check(spec, ctx, settings.path("reports_dir") / "evidence")
        state["results"].append(result)
        state["specs"][spec.test_id] = spec
        if result.status == PASS:
            return result
        if result.status == SKIPPED:
            pytest.skip(result.message)
        if result.status == ERROR:
            pytest.fail(f"[{spec.test_id}] AUTOMATION/ENVIRONMENT ERROR: {result.message}", pytrace=False)
        if result.known_defect:
            pytest.xfail(f"known defect {result.known_defect}: {result.message}")
        pytest.fail(f"[{spec.test_id}] {spec.title}\n  -> {result.message}\n  evidence: {result.evidence_file}", pytrace=False)

    return _run


def pytest_sessionfinish(session, exitstatus):
    st = session.config._qa
    if not st["results"] or session.config.getoption("--no-reports"):
        return
    ctx = st["ctx"]
    settings = load_settings()
    profile = {}
    if ctx is not None:
        for key, label in (("dist", "Distributor Sales file"), ("fact", "Fact Sales file"), ("cust", "Customer Master file")):
            if key in ctx._raw:
                profile[label] = len(ctx._raw[key])
        if "dm" in ctx._db_raw:
            profile["Data mart (MySQL)"] = len(ctx._db_raw["dm"])
    run_id = st["started"].strftime("%Y%m%d_%H%M%S")
    meta = build_meta(run_id, st["started"], time.perf_counter() - st["t0"], settings)
    results = sorted(st["results"], key=lambda r: r.test_id)
    write_reports(results, list(st["specs"].values()), settings.path("reports_dir"), profile, meta)
