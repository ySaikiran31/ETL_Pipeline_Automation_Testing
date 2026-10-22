# QA Validation Plan - Distributor Sales Data Reconciliation

*(Submission 1 - Study & Plan)*

## 1. Objective
Provide repeatable, automated evidence that distributor sales data is **complete, unique, correctly linked to customers, arithmetically
correct, and faithfully reflected in the Customer-360 data mart**, and report every violation with record-level evidence.

## 2. Scope
| In scope | Out of scope |
|---|---|
| Structure/content of the 3 source files | UI / report-layer (BI dashboard) testing |
| Source file -> MySQL source-table load fidelity | Performance / load testing beyond 50k-row volume |
| Distributor <-> Fact <-> Customer Master consistency | Fixing defects (QA is read-only: SELECT only) |
| Data-mart completeness, uniqueness, derivations, reference integrity | Security / access-control testing |
| Monetary calculations, product-family rules, mappings | Time-zone conversion (no zone attribute in data; flagged as risk) |

## 3. Test levels & approach
1. **File validation** - structure, encoding, delimiter, columns, mandatory, types, domains, formats, uniqueness (FIL, DST, FAC, CUS).
2. **Referential integrity** - sales -> Customer Master (REF).
3. **Load reconciliation** - file vs table: counts, keys, every field of every record (REC-001..009), and Distributor vs Fact (REC-010/011).
4. **Target reconciliation** - the data mart is *recomputed independently in pandas from the files* and compared record-by-record and by aggregate (REC-020..026) + SQL evidence (DBQ).
5. **Business rules** - calculations, product-family, key<->code mapping, temporal (CAL, PRD, MAP, BR).
6. **Data-mart rules** - domains, derivations, flags, lineage, enrichment (DM).
7. **Framework self-tests** - synthetic data proves checks have no false alarms and detect injected defects (`tests/unit`).

PASS/FAIL semantics: **PASS** = zero violations; **FAIL** = >=1 violating record (evidence CSV produced); **ERROR** = automation/environment
fault (not a data verdict); **SKIPPED** = prerequisite missing or *not evaluable* (e.g. customer status when no sale resolves to a customer) - never counted as PASS.

## 4. Risk-based priorities
| Priority | Risk | Examples |
|---|---|---|
| Critical | Financial misstatement / broken reconciliation | missing/extra/duplicate txns, orphan customer references, wrong amounts, non-APPROVED in mart |
| High | Incorrect attribution / mapping | key<->code mapping, family derivation, duplicate customer ids, null customer references |
| Medium | Data-quality hygiene | formats, optional-field blank-rates, temporal sanity |
| Low | Cosmetic | whitespace, load timestamp |

## 5. Environments & tools
Python 3.10+, pandas, mysql-connector-python, pytest, openpyxl; MySQL 8.0 (`python_project2`); read-only DB user; Git.
Config in `config/*.json`; secrets only via environment (`QA_DB_PASSWORD`).

## 6. Entry / exit criteria
**Entry:** the 3 files present; MySQL reachable; admin scripts 01-03 executed (sources + data mart loaded); DB user has SELECT.
**Exit:** all Critical/High validations PASS *or* each FAIL has a logged defect with owner; no ERROR; SKIPPED items explained; reports archived.

## 7. Defect analysis categories (per QA lifecycle)
Source-data defect - Customer Master defect - Database/ETL (data mart) defect - Mapping/Reference issue - Business-rule violation - Test-data problem - Automation defect - Environment/configuration. Each result carries a `defect_area` and a suggested owner in `defect_log.csv`.

## 8. Deliverables map
| Deliverable | Where |
|---|---|
| QA plan | this document |
| Data dictionary & mapping | `docs/Data_Dictionary_and_Source_Target_Mapping.md`, `config/schema.json` |
| Test scenario inventory / detailed test cases | `reports/test_case_inventory.csv` (generated; `python run_qa.py --list-checks`) |
| Automation framework | `src/`, `tests/`, `sql/`, `config/` |
| Execution logs | `logs/execution.log` |
| PASS/FAIL results, reconciliation, defects | `reports/validation_results.csv`, `reconciliation_report.csv`, `defect_log.csv`, `evidence/` |
| Executive QA report | `reports/qa_summary.html`, `reports/qa_report.xlsx` |

## 9. Known assumptions / open questions for the BA
1. Customer join key: the mart joins `Distributor.customer_id (CUST...)` to `Master.customer_id (CUC...)` - formats never overlap. Intended key?
2. Rules marked **INF** in the data dictionary need confirmation.
3. `customer_id` is not unique in the Customer Master (1,254 repeated ids) - is it a business key?
4. Date strings are `m/d/yyyy`; ambiguous day/month values are parsed using the formats listed in `config.json -> execution.date_formats`.
