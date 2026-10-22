USE python_project2;

INSERT INTO dm_Distributor_Sales_Customer_360 (
    dm_sk,
    sales_sk,
    distributor_txn_id,
    policy_number,
    customer_key,
    customer_id,

    sale_date,
    sale_date_key,
    distributor_code,
    distributor_name,

    product_code,
    product_name_raw,
    product_type_raw,
    product_family,
    product_category,

    folio_number,
    region_code,
    region_key,
    status,

    customer_pan,
    first_name,
    last_name,
    gender,
    date_of_birth,
    customer_age,

    email,
    mobile,
    city,
    state,
    pincode,
    country,

    kyc_status,
    customer_segment,
    annual_income,
    customer_onboarded_on,
    customer_active_flag,

    gross_amount,
    net_amount,
    commission_amount,
    tax_amount,
    discount_amount,

    premium_amount,
    sum_assured,
    units_allocated,
    nav_at_purchase,

    commission_pct,
    txn_count,

    is_new_customer_flag,
    is_high_value_flag,
    is_kyc_verified_flag,
    is_ins_txn_flag,
    is_mf_txn_flag,

    src_created_at,
    src_updated_at,
    fact_etl_run_id,
    dm_etl_run_id,
    dm_load_ts_utc
)

SELECT
    ROW_NUMBER() OVER (ORDER BY f.sales_sk) AS dm_sk,

    f.sales_sk,
    f.distributor_txn_id,
    f.policy_number,

    d2.customer_key,

    COALESCE(d1.customer_id, d2.customer_id) AS customer_id,

    d1.sale_date,
    f.sale_date_key,

    d1.distributor_code,
    d1.distributor_name,

    d1.product_code,
    d1.product_name_raw,
    d1.product_type_raw,

    CASE
        WHEN d1.product_code LIKE 'INS%' THEN 'INS'
        WHEN d1.product_code LIKE 'MF%' THEN 'MF'
        ELSE 'MF'
    END AS product_family,

    CASE
        WHEN d1.product_type_raw IN
             ('INS','Insurance','ULIP')
            THEN 'INSURANCE'

        WHEN d1.product_type_raw IN
             ('MF','SIP','Equity Fund','Debt Fund')
            THEN 'MUTUAL_FUND'

        ELSE 'MUTUAL_FUND'
    END AS product_category,

    d1.folio_number,
    d1.region_code,

    f.region_key,
    f.status,

    d2.customer_pan,
    d2.first_name,
    d2.last_name,
    d2.gender,
    d2.date_of_birth,

    CASE
        WHEN d2.date_of_birth IS NULL THEN NULL
        ELSE TIMESTAMPDIFF(
            YEAR,
            d2.date_of_birth,
            d1.sale_date
        )
    END AS customer_age,

    d2.email,
    d2.mobile,
    d2.city,
    d2.state,
    d2.pincode,
    d2.country,

    d2.kyc_status,
    d2.customer_segment,
    d2.annual_income,

    d2.onboarded_on AS customer_onboarded_on,
    d2.active_flag AS customer_active_flag,

    f.gross_amount,
    f.net_amount,
    f.commission_amount,
    f.tax_amount,
    f.discount_amount,

    f.premium_amount,
    f.sum_assured,
    f.units_allocated,
    f.nav_at_purchase,

    f.commission_pct,
    f.txn_count,

    f.is_new_customer_flag,
    f.is_high_value_flag,

    CASE
        WHEN d2.kyc_status = 'VERIFIED' THEN 'Y'
        ELSE 'N'
    END AS is_kyc_verified_flag,

    CASE
        WHEN d1.product_code LIKE 'INS%' THEN 'Y'
        ELSE 'N'
    END AS is_ins_txn_flag,

    CASE
        WHEN d1.product_code LIKE 'MF%' THEN 'Y'
        ELSE 'N'
    END AS is_mf_txn_flag,

    f.src_created_at,
    f.src_updated_at,

    f.etl_run_id AS fact_etl_run_id,

    'DM-ETL-20260715-01' AS dm_etl_run_id,

    UTC_TIMESTAMP() AS dm_load_ts_utc

FROM Fact_Sales f

INNER JOIN dim_Distributor_sales d1
    ON f.distributor_txn_id = d1.distributor_txn_id
   AND f.policy_number = d1.policy_number

LEFT JOIN dim_Customer_Master d2
    ON d1.customer_id = d2.customer_id

WHERE f.status = 'APPROVED';