#!/usr/bin/env python
"""Stand-alone QA runner.

Examples
    python run_qa.py                      # run everything
    python run_qa.py --skip-db            # file-only validations (no MySQL needed)
    python run_qa.py --suite reconciliation datamart_validation
    python run_qa.py --only REF-001 DM-007
    python run_qa.py --list-checks        # print the test-case inventory
Exit code: 0 = no new FAIL/ERROR, 1 = failures/errors found, 2 = framework/config problem.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from datetime import datetime

import pandas as pd

from src.config import load_settings
from src.context import QAContext
from src.logger import setup_logging, get_logger
from src.registry import CHECKS, load_all_checks
from src.report_generator import build_meta, inventory, write_reports
from src.results import ERROR, FAIL, SKIPPED
from src.runner import run_checks

SUITE_ORDER = ["file_validation", "sales_validation", "customer_validation", "database_validation",
               "reconciliation", "business_rules", "datamart_validation"]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Distributor Sales reconciliation QA runner")
    p.add_argument("--config", help="path to config.json (default config/config.json)")
    p.add_argument("--input-dir", help="folder holding the 3 source files (overrides config)")
    p.add_argument("--skip-db", action="store_true", help="skip every MySQL-dependent validation")
    p.add_argument("--suite", nargs="+", choices=SUITE_ORDER, help="run only these suites")
    p.add_argument("--only", nargs="+", metavar="TEST_ID", help="run only these test ids")
    p.add_argument("--list-checks", action="store_true", help="list all registered validations and exit")
    p.add_argument("--no-archive", action="store_true", help="do not keep a timestamped copy of the reports")
    p.add_argument("--exit-zero", action="store_true", help="always exit 0 (reporting-only mode)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.input_dir:
        os.environ["QA_INPUT_DIR"] = args.input_dir
    try:
        settings = load_settings(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    load_all_checks()
    specs = sorted(CHECKS.values(), key=lambda s: (SUITE_ORDER.index(s.suite), s.test_id))
    if args.list_checks:
        pd.set_option("display.width", 220, "display.max_colwidth", 90, "display.max_rows", 500)
        print(inventory(specs)[["test_id", "module", "priority", "validation_type", "scenario"]].to_string(index=False))
        print(f"\n{len(specs)} validations registered")
        return 0
    if args.suite:
        specs = [s for s in specs if s.suite in args.suite]
    if args.only:
        wanted = {w.upper() for w in args.only}
        unknown = wanted - set(CHECKS)
        if unknown:
            print(f"Unknown test id(s): {sorted(unknown)}", file=sys.stderr)
            return 2
        specs = [s for s in specs if s.test_id in wanted]

    log = setup_logging(settings.path("logs_dir"))
    log = get_logger("run")
    if not args.skip_db and not settings.db.get("password") and sys.stdin.isatty():
        settings.db_password = getpass.getpass(f"MySQL password for {settings.db['user']} (blank = none): ") or None

    started = datetime.now()
    run_id = started.strftime("%Y%m%d_%H%M%S")
    t0 = time.perf_counter()
    log.info("=== QA RUN %s START: %d validations (skip_db=%s) ===", run_id, len(specs), args.skip_db)
    ctx = QAContext(settings, db_enabled=not args.skip_db)
    reports_dir = settings.path("reports_dir")
    try:
        results = run_checks(specs, ctx, reports_dir / "evidence")
        profile = {}
        for key, label in (("dist", "Distributor Sales file"), ("fact", "Fact Sales file"), ("cust", "Customer Master file")):
            if key in ctx._raw:
                profile[label] = len(ctx._raw[key])
        if "dm" in ctx._db_raw:
            profile["Data mart (MySQL)"] = len(ctx._db_raw["dm"])
        meta = build_meta(run_id, started, time.perf_counter() - t0, settings)
        out = write_reports(results, specs, reports_dir, profile, meta, archive=not args.no_archive)
    finally:
        ctx.close()

    c = pd.Series([r.status for r in results]).value_counts()
    print("\n" + "=" * 78)
    print(f" QA RUN {run_id}  |  {len(results)} validations  |  PASS {c.get('PASS', 0)}  FAIL {c.get(FAIL, 0)}  "
          f"ERROR {c.get(ERROR, 0)}  SKIPPED {c.get(SKIPPED, 0)}")
    print("=" * 78)
    for r in sorted((r for r in results if r.status in (FAIL, ERROR)), key=lambda r: (["Critical", "High", "Medium", "Low"].index(r.severity), r.test_id)):
        print(f" [{r.status:5}] {r.test_id:8} {r.severity:8} {r.title[:62]}  ({r.failed_records:,} failed)")
    print(f"\n HTML summary : {out['qa_summary']}\n Defect log   : {out['defect_log']}\n Evidence dir : {reports_dir / 'evidence'}\n")
    new = [r for r in results if r.status in (FAIL, ERROR) and not r.known_defect]
    return 0 if (args.exit_zero or not new) else 1


if __name__ == "__main__":
    sys.exit(main())
