# Distributor Sales Data Reconciliation - Python QA Automation Framework

An ETL / BI data-QA framework that validates **three sources** (Distributor Sales JSON, Fact Sales CSV, Customer Master TXT) against the
**MySQL source tables and the `dm_Distributor_Sales_Customer_360` data mart**: completeness, uniqueness, referential integrity,
source-to-target reconciliation, calculations and business rules - with PASS/FAIL results, record-level evidence, a defect log and an executive report.

* **131 automated validations** in 15 modules, every one with ID, severity, category and evidence
* **Two ways to run** from one registry: `python run_qa.py` (stand-alone) and `pytest` (CI-friendly)
* **118 framework self-tests** on synthetic data (no false alarms on clean data; 36 injected defects all detected)
* Read-only against the DB (SELECT only), secrets via environment, full logging, modular and data-driven

---------------------------------------------------------------------------------------------------

## 1. Project layout

```
distributor-sales-qa/
├── run_qa.py                    # stand-alone runner (CLI)
├── conftest.py / pytest.ini     # pytest wiring (one test per validation)
├── requirements.txt  .env.example  .gitignore
├── config/
│   ├── config.json              # paths, file names/delimiters, DB, execution settings, known_defects
│   ├── business_rules.json      # domains, regex patterns, thresholds, product-family rules (DOC vs INF)
│   └── schema.json              # column types/lengths/nullability (generated from the DDL)
├── data/                        # put the 3 source files here (or set QA_INPUT_DIR)
├── sql/
│   ├── validation_queries.sql   # 17 named SQL validations (each returns offending rows)
│   └── lab_setup/               # your admin 01-03 scripts (reference copy)
├── src/
│   ├── file_reader.py (+_core)  # loaders, encoding detection, FIL-001..012
│   ├── sales_validator.py       # Distributor (DST) + Fact (FAC) content checks
│   ├── customer_validator.py    # Customer Master (CUS) + customer reference integrity (REF)
│   ├── database.py              # MySQL access, named SQL, DB-001..004, DBQ-001..017
│   ├── reconciliation.py        # comparison engine, expected data-mart builder, REC checks
│   ├── business_rules.py        # calculations (CAL), product family (PRD), mappings (MAP), temporal (BR)
│   ├── datamart_validator.py    # data mart checks (DM)
│   ├── validators.py            # reusable validation primitives
│   ├── normalizer.py            # type parsing - same code path for file and DB values
│   ├── context.py runner.py registry.py results.py config.py logger.py
│   └── report_generator.py      # CSV / HTML / Excel / defect log
├── tests/                       # pytest modules + tests/unit (framework self-tests)
├── tools/generate_schema.py     # regenerate config/schema.json from DDL
├── docs/                        # QA plan, data dictionary & mapping, findings report
├── reports/  logs/              # generated output
```

## 2. One-time setup (Windows / PowerShell shown; macOS/Linux equivalent in brackets)

```powershell
# 1. unzip the framework, e.g. to C:\qa-lab\distributor-sales-qa
cd C:\qa-lab\distributor-sales-qa
python -m venv .venv
.\.venv\Scripts\Activate.ps1               # [source .venv/bin/activate]
pip install -r requirements.txt

# 2. make sure the lab environment is loaded (your existing admin scripts - unchanged)
#    01_create_source_tables.sql -> admin\load_sources.py -> 02_create_datamart.sql -> 03_load_datamart.sql

# 3. tell the framework where the data is and how to connect (never put the password in a file under Git)
copy .env.example .env                      # edit QA_DB_PASSWORD (and QA_INPUT_DIR if files are not in .\data)
#    or use the 3 files directly from the lab folder:
#    $env:QA_INPUT_DIR = "C:\qa-lab\python-project-2\input"
```

The DB user (`python_p2_learner`) only needs **SELECT** on `python_project2`.

## 3. How to execute (recommended order)

| Step | Command | Purpose |
|---|---|---|
| 0 | `pytest tests/unit` | Prove the framework itself works (needs no data, no DB). Expect **118 passed**. |
| 1 | `python run_qa.py --list-checks` | See the full test-case inventory. |
| 2 | `python run_qa.py --skip-db` | File-only validations (no MySQL) - fastest feedback on source data. |
| 3 | `python run_qa.py` | **Full run** (files + MySQL + reconciliation + data mart). ~30-40 s for 50k rows. |
| 4 | open `reports\qa_summary.html` | Executive report. Drill into `reports\evidence\<TEST-ID>.csv`. |
| 5 | `python run_qa.py --only REF-001 DM-007` | Re-run specific validations (e.g. after a fix). |
| 6 | `pytest` (or `pytest -m "not db"`, `pytest -k REF`) | Same validations as pytest tests (CI). Reports are written at the end. |

Useful options: `--suite reconciliation datamart_validation`, `--input-dir <path>`, `--no-archive`, `--exit-zero`.
With pytest use the `=` form: `pytest --input-dir=C:\qa-lab\python-project-2\input` (a space makes pytest treat the path as a test target).

**Exit code:** `0` = no new FAIL/ERROR - `1` = failures/errors found - `2` = configuration problem. Failures listed in `config.json -> known_defects`
(e.g. `{"REF-001": "DEF-123"}`) are shown as known and don't fail the run (xfail in pytest).

## 4. What gets produced

| File | Content |
|---|---|
| `reports/qa_summary.html` | Overall PASS/FAIL, KPIs, results by module, QA metrics (missing/extra/duplicates/customer/product/calculation/mismatch/business-rule), defect list, filterable result table |
| `reports/validation_results.csv` | One row per validation: status, totals, failed count, message, evidence path, duration |
| `reports/defect_log.csv` | One row per FAIL/ERROR: defect id, severity, root-cause area, suggested owner, sample evidence, how to reproduce |
| `reports/reconciliation_report.csv` | Compared / matched / mismatched for every reconciliation |
| `reports/evidence/<ID>.csv` | The offending records for each failed validation (capped at 5,000 rows; counts are always exact) |
| `reports/test_case_inventory.csv` | Generated test-case catalogue (ID, scenario, type, priority, source, preconditions) |
| `reports/qa_report.xlsx` | All of the above in one workbook |
| `logs/execution.log` | Step-by-step execution log (rotating) |
| `reports/archive/<run_id>/` | Timestamped copy of every run |

## 5. Validation catalogue

| Module | IDs | # | What it proves |
|---|---|---|---|
| File Structure | FIL-001..012 | 12 | exists, readable, encoding auto-detected (UTF-8/UTF-16), columns, delimiter, malformed rows, record count |
| Distributor Sales | DST-001..018 | 18 | mandatory, unique txn/policy, formats, dates, amounts, domains, blank-rates, truncation, whitespace |
| Fact Sales | FAC-001..012 | 12 | mandatory, unique keys, numerics, DDL CHECK rules, flags, dates, date-key, blank-rate |
| Customer Master | CUS-001..013 | 13 | mandatory, unique keys, duplicate/conflicting customer_id, formats, domains, age rules |
| Customer Reference | REF-001..007 | 7 | sales -> master integrity (id & key), 1:1 mapping, null consistency, PAN agreement, inactive/KYC, orphan customers |
| Database | DB-001..004 | 4 | connection, tables, columns/types, row counts |
| SQL validations | DBQ-001..017 | 17 | duplicates, orphans, missing/extra, enrichment, measures and attributes vs sources (all in `sql/validation_queries.sql`) |
| Load reconciliation | REC-001..009 | 9 | file vs table: counts, keys, **every field of every record** |
| Cross-source | REC-010..011 | 2 | Distributor vs Fact coverage and field agreement |
| Target reconciliation | REC-020..026 | 7 | expected-vs-mart: count, missing, extra, fact/distributor/customer fields, aggregates by dimension |
| Calculations | CAL-001..008 | 8 | net, commission %, units x NAV, insurance amounts, precision, high-value flag (file and mart) |
| Product & family | PRD-001..005 | 5 | prefix, type/family combination, family field population, key/code, name/code |
| Key/code mapping | MAP-001..003 | 3 | region/distributor/product key <-> code |
| Business/temporal | BR-001..002 | 2 | sale date vs created date, date key drift |
| Data mart | DM-001..012 | 12 | mandatory, domains, family, values, enrichment, age, lineage, dm_sk, flags, customer attribution |

Checks that cannot be evaluated because an upstream defect removes the data they need are **SKIPPED ("BLOCKED")**, never a silent PASS
(e.g. DM-006 customer_age while no mart row has a customer).

## 6. How it works (architecture)

```
load_settings -> QAContext (lazy, cached datasets) -> registry of @qa_check functions -> runner -> CheckResult(+evidence) -> report_generator
files --parse--> typed frames ----\
                                   >-- compare_frames()  (outer-join on key, NULL-safe, field by field)
MySQL --SELECT--> stringified -> typed -/
files --pandas re-implementation of the documented ETL--> expected data mart --compare--> actual data mart
```
* **Normalise before compare:** DB values are stringified and parsed by the *same* functions as file values.
* **Independent oracle:** the expected data mart is rebuilt from the files with pandas, not from the ETL SQL, so ETL logic errors are caught.
* **Failure isolation:** exceptions become ERROR (automation/environment), prerequisite problems become SKIPPED - one bad check never stops the run.
* **Traceability:** every failure = test ID + rule + exact records + defect-area + owner.

## 7. Extending the framework

```python
# src/business_rules.py  (any module under src/ that is imported by registry.load_all_checks)
@qa_check("BR-003", suite="business_rules", module="Business Rule Validation", category="Business rule",
          severity="High", dataset="Fact Sales (CSV)", title="Commission not paid on CANCELLED sales", requires=["fact"])
def br_no_commission_on_cancelled(ctx):
    f = ctx.raw("fact"); t = ctx.typed("fact")
    bad = (f["status"] == "CANCELLED") & (t["commission_amount"] > 0)
    return v.rows_outcome(f, bad, "sales_sk", ["status", "commission_amount"], "Commission on cancelled sale")
```
New SQL check: add a `-- name:` block to `sql/validation_queries.sql` and one line to `SQL_CHECKS` in `database.py`.
Change a threshold/domain: edit `config/business_rules.json`. New column in the DDL: re-run `python tools/generate_schema.py <admin-dir>`.
Add a test for the new rule in `tests/unit/test_framework.py` (clean-data + injected-defect pair).

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `DB-001 FAIL ... Access denied` | wrong `QA_DB_PASSWORD`/user; confirm with `mysql -u python_p2_learner -p python_project2` |
| Many checks SKIPPED "Database unavailable" | DB down / wrong host or port; or run with `--skip-db` deliberately |
| `FIL-001 FAIL File not found` | files not in `data/` - set `QA_INPUT_DIR`; lookup is case-insensitive |
| Everything blank / odd characters | encoding: UTF-8 and UTF-16 (BOM or not) are auto-detected; cp1252 fallback |
| `unrecognized arguments: --input-dir` | use `--input-dir=PATH` (with `=`) in pytest |
| ERROR status | automation/environment fault - see traceback in `logs/execution.log` |
| Dates mis-parsed | adjust `execution.date_formats` / `datetime_formats` in `config.json` |

## 9. Real results on the lab data

See `docs/QA_Findings_Report.md` and the sample output in `docs/sample_output/` (produced by this exact code against your zip's data loaded into MySQL 8.0).
