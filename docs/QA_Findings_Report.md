# QA Findings Report - Distributor Sales Reconciliation

**Run:** full suite (131 validations) against the lab data (3 files x 50,000 records) loaded into MySQL 8.0 with the lab's own admin scripts 01-03.
**Result:** 116 PASS - **12 FAIL** (4 Critical, 6 High, 2 Medium) - 0 ERROR - 3 SKIPPED (blocked by finding F1).
**Overall status: FAIL.**  The 12 failures trace back to **6 root causes**.

## What passed (confidence statement)
* File structure: all 3 files readable, expected columns, no malformed records, 50,000 records each.
* Distributor, Fact, Customer Master: mandatory fields, unique transaction/policy/sales keys, formats, domains, dates, no truncation.
* **Load reconciliation:** all 3 files match their MySQL tables on count, keys and every field of every record.
* **Distributor vs Fact:** identical transaction sets; policy, gross, commission, status, timestamps and sale date agree for all 50,000.
* **Calculations:** net = gross - commission, commission %, units x NAV, insurance amounts, 2-dp precision, high-value flag - 100% conform, in source and in the mart.
* **Data mart vs independent pandas recomputation:** 45,076 rows = all APPROVED transactions, no missing, no extra, every field and every aggregate (overall / by category / distributor / region) matches. REJECTED/CANCELLED excluded. No duplicates; no orphans to Fact/Distributor.

## Findings (root causes)

| # | Sev | Root cause | Evidence (tests) | Impact |
|---|---|---|---|---|
| **F1** | Critical | **Sales cannot be linked to the Customer Master.** Distributor `customer_id` is `CUST<n>` (44,753 distinct ids); master `customer_id` is `CUC<n>`. Fact `customer_key` ranges 100,004-400,000 whereas master keys are 1-50,000. **0 of 48,461** populated references resolve. | REF-001, REF-002, DM-007, DBQ-013 | The Customer-360 mart has **no customer attributes in any row** (43,685 rows with a customer_id are un-enriched). Blocked checks: REF-006, DM-005, DM-006 (cannot assess KYC/active status, age, partial enrichment). |
| **F2** | High | **Customer Master `customer_id` is not unique:** 1,254 ids shared by 2,525 records, with conflicting PAN/DOB (different people, same id). | CUS-004, CUS-005, DBQ-006 | If F1 is fixed by joining on `customer_id`, these ids would fan-out the join (duplicate mart rows / violate the mart's unique txn constraint) or mis-attribute sales. |
| **F3** | High | **1,539 source sales (3.08%) have no customer reference** (blank `customer_id` / `customer_key`, consistent between the two sources); 1,391 of them are in the mart. | FAC-012, DST-015, DM-012 | Those sales can never be attributed to a customer. |
| **F4** | High | **`region_code` blank for 8,315 records (16.6%)**, all with `region_key` = 1 (which is NORTH in every populated row). | MAP-002, DST-015 | Region reporting in the mart is understated/blank for NORTH. |
| **F5** | Medium | **`distributor_name` is 100% blank** in the Distributor feed. | DST-015 | Mart `distributor_name` is NULL for all rows. |
| **F6** | Medium | **PAN:** 9.9% of distributor records have no PAN, and where both exist the PAN differs from the Customer Master's PAN for all 45,035 policy-linked pairs *(link via `policy_number` is inferred - confirm with BA)*. | REF-005, DST-015 | Identity attributes disagree across systems. |

## Recommendations
1. Confirm the intended customer join key with the BA/mapping owner (F1). Until resolved the mart should not be used for customer analytics.
2. Make `customer_id` unique (or define a deterministic survivorship rule) in the master before changing the join (F2).
3. Agree handling of sales without a customer (F3) and fix the region / distributor-name extraction in the feed (F4, F5).
4. Re-run `python run_qa.py` after fixes; blocked checks (REF-006, DM-005, DM-006) will then become evaluable.

## Notes on test evidence
`docs/sample_output/qa_summary.html` is the executive report; each finding has a record-level CSV in `docs/sample_output/evidence/` (capped at 5,000 rows; counts above are exact).
