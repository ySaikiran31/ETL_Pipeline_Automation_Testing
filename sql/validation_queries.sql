-- ============================================================================
-- Named validation queries (MySQL 8.0).  Placeholders {dist} {fact} {cust} {dm}
-- are replaced with the table names from config/config.json.
-- Convention: every query returns the OFFENDING ROWS (0 rows = PASS).
-- All queries are read-only (SELECT).
-- ============================================================================

-- name: dm_dup_txn
SELECT distributor_txn_id, COUNT(*) AS occurrences
FROM {dm} GROUP BY distributor_txn_id HAVING COUNT(*) > 1;

-- name: dm_dup_policy
SELECT policy_number, COUNT(*) AS occurrences
FROM {dm} GROUP BY policy_number HAVING COUNT(*) > 1;

-- name: dm_dup_sales_sk
SELECT sales_sk, COUNT(*) AS occurrences
FROM {dm} GROUP BY sales_sk HAVING COUNT(*) > 1;

-- name: dist_dup_txn
SELECT distributor_txn_id, COUNT(*) AS occurrences
FROM {dist} GROUP BY distributor_txn_id HAVING COUNT(*) > 1;

-- name: fact_dup_txn
SELECT distributor_txn_id, COUNT(*) AS occurrences
FROM {fact} GROUP BY distributor_txn_id HAVING COUNT(*) > 1;

-- name: cust_dup_customer_id
SELECT customer_id, COUNT(*) AS occurrences, MIN(customer_key) AS first_key, MAX(customer_key) AS last_key
FROM {cust} GROUP BY customer_id HAVING COUNT(*) > 1;

-- name: dm_orphan_fact
SELECT m.dm_sk, m.sales_sk, m.distributor_txn_id
FROM {dm} m LEFT JOIN {fact} f ON f.sales_sk = m.sales_sk
WHERE f.sales_sk IS NULL;

-- name: dm_orphan_dist
SELECT m.dm_sk, m.distributor_txn_id, m.policy_number
FROM {dm} m LEFT JOIN {dist} d ON d.distributor_txn_id = m.distributor_txn_id AND d.policy_number = m.policy_number
WHERE d.distributor_txn_id IS NULL;

-- name: dm_orphan_customer
SELECT m.dm_sk, m.distributor_txn_id, m.customer_key
FROM {dm} m LEFT JOIN {cust} c ON c.customer_key = m.customer_key
WHERE m.customer_key IS NOT NULL AND c.customer_key IS NULL;

-- name: dm_non_approved
SELECT dm_sk, distributor_txn_id, status FROM {dm} WHERE status <> 'APPROVED';

-- name: approved_missing_in_dm
SELECT f.sales_sk, f.distributor_txn_id, f.status
FROM {fact} f
JOIN {dist} d ON d.distributor_txn_id = f.distributor_txn_id AND d.policy_number = f.policy_number
WHERE f.status = 'APPROVED'
  AND NOT EXISTS (SELECT 1 FROM {dm} m WHERE m.sales_sk = f.sales_sk);

-- name: dm_extra_vs_source
SELECT m.dm_sk, m.sales_sk, m.distributor_txn_id, m.status
FROM {dm} m
WHERE NOT EXISTS (SELECT 1 FROM {fact} f
                  JOIN {dist} d ON d.distributor_txn_id = f.distributor_txn_id AND d.policy_number = f.policy_number
                  WHERE f.sales_sk = m.sales_sk AND f.status = 'APPROVED');

-- name: dm_customer_not_enriched
SELECT m.dm_sk, m.distributor_txn_id, m.customer_id, m.customer_key, m.first_name, m.kyc_status
FROM {dm} m
WHERE m.customer_id IS NOT NULL AND m.customer_key IS NULL;

-- name: dm_vs_fact_measures
SELECT m.sales_sk, m.distributor_txn_id,
       m.gross_amount AS dm_gross, f.gross_amount AS fact_gross,
       m.net_amount AS dm_net, f.net_amount AS fact_net,
       m.commission_amount AS dm_commission, f.commission_amount AS fact_commission,
       m.tax_amount AS dm_tax, f.tax_amount AS fact_tax,
       m.discount_amount AS dm_discount, f.discount_amount AS fact_discount
FROM {dm} m JOIN {fact} f ON f.sales_sk = m.sales_sk
WHERE NOT (m.gross_amount <=> f.gross_amount) OR NOT (m.net_amount <=> f.net_amount)
   OR NOT (m.commission_amount <=> f.commission_amount) OR NOT (m.tax_amount <=> f.tax_amount)
   OR NOT (m.discount_amount <=> f.discount_amount) OR NOT (m.premium_amount <=> f.premium_amount)
   OR NOT (m.sum_assured <=> f.sum_assured) OR NOT (m.units_allocated <=> f.units_allocated)
   OR NOT (m.nav_at_purchase <=> f.nav_at_purchase) OR NOT (m.commission_pct <=> f.commission_pct);

-- name: dm_vs_dist_attributes
SELECT m.distributor_txn_id,
       m.sale_date AS dm_sale_date, d.sale_date AS src_sale_date,
       m.distributor_code AS dm_distributor, d.distributor_code AS src_distributor,
       m.product_code AS dm_product, d.product_code AS src_product,
       m.region_code AS dm_region, d.region_code AS src_region,
       m.folio_number AS dm_folio, d.folio_number AS src_folio
FROM {dm} m JOIN {dist} d ON d.distributor_txn_id = m.distributor_txn_id
WHERE NOT (m.sale_date <=> d.sale_date) OR NOT (m.distributor_code <=> d.distributor_code)
   OR NOT (m.product_code <=> d.product_code) OR NOT (m.region_code <=> d.region_code)
   OR NOT (m.folio_number <=> d.folio_number) OR NOT (m.policy_number <=> d.policy_number);

-- name: fact_vs_dist_core
SELECT f.distributor_txn_id,
       f.policy_number AS fact_policy, d.policy_number AS dist_policy,
       f.gross_amount AS fact_gross, d.gross_amount AS dist_gross,
       f.commission_amount AS fact_commission, d.commission_amount AS dist_commission,
       f.status AS fact_status, d.status AS dist_status
FROM {fact} f JOIN {dist} d ON d.distributor_txn_id = f.distributor_txn_id
WHERE NOT (f.policy_number <=> d.policy_number) OR NOT (f.gross_amount <=> d.gross_amount)
   OR NOT (f.commission_amount <=> d.commission_amount) OR NOT (f.status <=> d.status)
   OR NOT (f.src_created_at <=> d.created_at) OR NOT (f.src_updated_at <=> d.updated_at);

-- name: dm_future_load_ts
SELECT dm_sk, distributor_txn_id, dm_load_ts_utc FROM {dm} WHERE dm_load_ts_utc > UTC_TIMESTAMP();
