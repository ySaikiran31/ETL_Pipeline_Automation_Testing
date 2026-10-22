# Data Dictionary & Source-to-Target Mapping

## 1. Data sources (what the lab really contains)

| # | Source | File / table | Format | Rows | Key | Role |
|---|---|---|---|---|---|---|
| S1 | Distributor Sales | `dim_Distributor_sales_50k.json` -> `dim_Distributor_sales` | JSON array of 17-field objects | 50,000 | `distributor_txn_id` (also unique `policy_number`) | Distributor-provided raw transactions |
| S2 | Fact Sales | `Fact_Sales_50k_CSV.csv` -> `Fact_Sales` | comma-delimited, header row, 27 columns | 50,000 | `sales_sk` (also unique txn id + policy) | Conformed fact (keys, measures, flags) |
| S3 | Customer Master | `dim_Customer_Master_50k.txt` -> `dim_Customer_Master` | comma-delimited TXT, 22 columns | 50,000 | `customer_key` (unique `policy_number`); `customer_id` is a *non-unique* business id | Customer reference / attributes |
| T  | **Target** | `dm_Distributor_Sales_Customer_360` | MySQL table, 57 columns | 45,076 | `dm_sk`; unique `distributor_txn_id`, `policy_number`, `sales_sk` | Customer-360 data mart |

> The generic project PDFs describe a *pipe-delimited* TXT and a table called `Fact_Sales` as the target. The lab package actually delivers
> JSON + CSV + TXT sources and a **data mart** as the target. The framework is built for the real lab; file layout, delimiter, and table
> names are all configurable in `config/config.json`.

Column-level definitions (name, type, length, nullability) live in `config/schema.json`, generated from the DDL by `tools/generate_schema.py`.

## 2. Load lineage

```
JSON/CSV/TXT files --(admin/load_sources.py)--> dim_Distributor_sales, Fact_Sales, dim_Customer_Master
                                                       |
                         (admin/03_load_datamart.sql)  v
        Fact_Sales (status='APPROVED')  JOIN  dim_Distributor_sales (txn_id + policy_number)
                                        LEFT JOIN dim_Customer_Master (customer_id)
                                                       v
                                      dm_Distributor_Sales_Customer_360
```

## 3. Source -> target mapping (data mart)

| Target column(s) | Source | Rule | Validated by |
|---|---|---|---|
| `sales_sk`, `sale_date_key`, `region_key`, `status`, `gross/net/commission/tax/discount_amount`, `premium_amount`, `sum_assured`, `units_allocated`, `nav_at_purchase`, `commission_pct`, `txn_count`, `is_new_customer_flag`, `is_high_value_flag`, `src_created_at/updated_at`, `fact_etl_run_id` | Fact_Sales | straight copy, **only `status='APPROVED'`** | REC-020..023, DBQ-010/014 |
| `distributor_txn_id`, `policy_number` | Fact_Sales + Distributor | join key (both must match) | REC-020..022, DBQ-008 |
| `sale_date`, `distributor_code/name`, `product_code`, `product_name_raw`, `product_type_raw`, `folio_number`, `region_code`, `customer_id` | Distributor Sales | straight copy (`customer_id` = COALESCE(distributor, master)) | REC-024, DBQ-015 |
| `product_family` | `product_code` | `INS%` -> INS, `MF%` -> MF, **else MF** | REC-024, DM-003, PRD-001 |
| `product_category` | `product_type_raw` | INS/Insurance/ULIP -> INSURANCE, else MUTUAL_FUND | REC-024, DM-003, PRD-002 |
| `is_ins_txn_flag`, `is_mf_txn_flag` | `product_code` prefix | Y/N | REC-024, DM-010 |
| `customer_key`, `customer_pan`, name, gender, DOB, e-mail, mobile, address, `kyc_status`, `customer_segment`, `annual_income`, onboarding, active flag | Customer Master | **LEFT JOIN on `customer_id`** | REC-025, DM-005, DM-007, REF-001 |
| `customer_age` | DOB, `sale_date` | full years (`TIMESTAMPDIFF(YEAR,...)`) | REC-025, DM-006 |
| `is_kyc_verified_flag` | `kyc_status` | VERIFIED -> Y | REC-025, DM-010 |
| `dm_sk`, `dm_etl_run_id`, `dm_load_ts_utc` | ETL | sequence by `sales_sk`; audit | DM-008, DM-009 |

## 4. Business rules (provenance)

`DOC` = stated in the DDL / SQL. `INF` = inferred from profiling the data (100% conformant today) - **confirm with the BA** before raising a defect.

| Rule | Provenance | Check |
|---|---|---|
| `status` in APPROVED/REJECTED/CANCELLED; product type, region, gender, KYC, segment domains | DOC (CHECK constraints) | DST-008..010, CUS-007 |
| `gross>0`, `net,tax,discount>=0`, `0<=commission<=gross`, `0<=commission_pct<=15`, `txn_count=1` | DOC | FAC-006, DM-004 |
| Data mart contains only APPROVED | DOC | DBQ-010, REC-022 |
| `net_amount = gross_amount - commission_amount` | INF | CAL-001, CAL-007 |
| `commission_pct = commission/gross*100` (3 dp) | INF | CAL-002, CAL-008 |
| MF: `units x NAV ~ gross`; MF has units/NAV/folio and no premium/sum assured; INS the reverse | INF | CAL-003, PRD-003 |
| `is_high_value_flag='Y'` iff `gross>=100000` | INF | CAL-006, DM-010 |
| `sale_date` = date of `created_at` | INF | BR-001 |
| Distributor `customer_id` format `CUST<digits>`, master `CUC<digits>` | INF | DST-012, CUS-006 |
| Same person -> same PAN in source and master (linked via `policy_number`) | INF | REF-005 |

Thresholds and domains are editable in `config/business_rules.json`.
