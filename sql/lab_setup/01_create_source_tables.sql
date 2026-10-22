USE python_project2;

-- ============================================================
-- PYTHON PROJECT 2
-- SOURCE TABLES
-- Based on Mapping_Document_Python_Project.xlsx
-- Sheets 3, 4 and 5
-- MySQL 8.0
-- ============================================================


-- ============================================================
-- 1. DIM_DISTRIBUTOR_SALES
-- Sheet 3
-- ============================================================

DROP TABLE IF EXISTS `dim_Distributor_sales`;

CREATE TABLE `dim_Distributor_sales` (

    `distributor_txn_id` VARCHAR(25) NOT NULL,

    `sale_date` DATE NOT NULL,

    `distributor_code` VARCHAR(20) NOT NULL,

    `distributor_name` VARCHAR(150) NULL,

    `customer_id` VARCHAR(15) NULL,

    `customer_pan` VARCHAR(10) NULL,

    `product_code` VARCHAR(30) NOT NULL,

    `product_name_raw` VARCHAR(200) NULL,

    `product_type_raw` VARCHAR(50) NOT NULL,

    `policy_number` VARCHAR(30) NOT NULL,

    `folio_number` VARCHAR(30) NULL,

    `gross_amount` DECIMAL(15,2) NOT NULL,

    `commission_amount` DECIMAL(15,2) NULL,

    `region_code` VARCHAR(20) NULL,

    `status` VARCHAR(20) NOT NULL,

    `created_at` DATETIME NOT NULL,

    `updated_at` DATETIME NOT NULL,

    PRIMARY KEY (`distributor_txn_id`),

    UNIQUE KEY `uk_dim_distributor_policy_number`
        (`policy_number`),

    CONSTRAINT `chk_dim_distributor_gross_amount`
        CHECK (`gross_amount` > 0),

    CONSTRAINT `chk_dim_distributor_commission`
        CHECK (
            `commission_amount` IS NULL
            OR (
                `commission_amount` >= 0
                AND `commission_amount` <= `gross_amount`
            )
        ),

    CONSTRAINT `chk_dim_distributor_status`
        CHECK (
            `status` IN (
                'APPROVED',
                'REJECTED',
                'CANCELLED'
            )
        ),

    CONSTRAINT `chk_dim_distributor_product_type`
        CHECK (
            `product_type_raw` IN (
                'MF',
                'SIP',
                'Equity Fund',
                'Debt Fund',
                'INS',
                'Insurance',
                'ULIP'
            )
        ),

    CONSTRAINT `chk_dim_distributor_region`
        CHECK (
            `region_code` IS NULL
            OR `region_code` IN (
                'NORTH',
                'SOUTH',
                'EAST',
                'WEST',
                'CENTRAL'
            )
        ),

    CONSTRAINT `chk_dim_distributor_dates`
        CHECK (`updated_at` >= `created_at`)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;


-- ============================================================
-- 2. DIM_CUSTOMER_MASTER
-- Sheet 5
-- ============================================================

DROP TABLE IF EXISTS `dim_Customer_Master`;

CREATE TABLE `dim_Customer_Master` (

    `customer_key` INT NOT NULL,

    `customer_id` VARCHAR(15) NOT NULL,

    `customer_pan` VARCHAR(10) NULL,

    `policy_number` VARCHAR(30) NOT NULL,

    `first_name` VARCHAR(50) NOT NULL,

    `last_name` VARCHAR(50) NOT NULL,

    `gender` CHAR(1) NOT NULL,

    `date_of_birth` DATE NOT NULL,

    `email` VARCHAR(100) NOT NULL,

    `mobile` VARCHAR(15) NOT NULL,

    `address_line` VARCHAR(200) NOT NULL,

    `city` VARCHAR(50) NOT NULL,

    `state` VARCHAR(50) NOT NULL,

    `pincode` VARCHAR(10) NOT NULL,

    `country` VARCHAR(50) NOT NULL,

    `kyc_status` VARCHAR(20) NOT NULL,

    `customer_segment` VARCHAR(20) NOT NULL,

    `annual_income` DECIMAL(15,2) NOT NULL,

    `onboarded_on` DATE NOT NULL,

    `active_flag` CHAR(1) NOT NULL,

    `created_at` DATETIME NOT NULL,

    `updated_at` DATETIME NOT NULL,

    PRIMARY KEY (`customer_key`),
   
    UNIQUE KEY `uk_dim_customer_policy_number`
        (`policy_number`),

    CONSTRAINT `chk_dim_customer_gender`
        CHECK (
            `gender` IN ('M','F','O')
        ),

    CONSTRAINT `chk_dim_customer_kyc`
        CHECK (
            `kyc_status` IN (
                'VERIFIED',
                'PENDING',
                'REJECTED'
            )
        ),

    CONSTRAINT `chk_dim_customer_segment`
        CHECK (
            `customer_segment` IN (
                'RETAIL',
                'HNI',
                'PREMIUM',
                'CORPORATE'
            )
        ),

    CONSTRAINT `chk_dim_customer_income`
        CHECK (`annual_income` >= 0),

    CONSTRAINT `chk_dim_customer_active`
        CHECK (
            `active_flag` IN ('Y','N')
        ),

    CONSTRAINT `chk_dim_customer_dates`
        CHECK (`updated_at` >= `created_at`)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;


-- ============================================================
-- 3. FACT_SALES
-- Sheet 4
-- ============================================================

DROP TABLE IF EXISTS `Fact_Sales`;

CREATE TABLE `Fact_Sales` (

    `sales_sk` BIGINT NOT NULL,

    `distributor_txn_id` VARCHAR(25) NOT NULL,

    `sale_date_key` INT NOT NULL,

    `distributor_key` INT NOT NULL,

    `product_key` INT NOT NULL,

    `customer_key` INT NULL,

    `region_key` INT NOT NULL,

    `gross_amount` DECIMAL(15,2) NOT NULL,

    `net_amount` DECIMAL(15,2) NOT NULL,

    `commission_amount` DECIMAL(15,2) NULL,

    `tax_amount` DECIMAL(15,2) NOT NULL,

    `discount_amount` DECIMAL(15,2) NOT NULL,

    `premium_amount` DECIMAL(15,2) NULL,

    `sum_assured` DECIMAL(15,2) NULL,

    `units_allocated` DECIMAL(15,4) NULL,

    `nav_at_purchase` DECIMAL(15,4) NULL,

    `commission_pct` DECIMAL(6,3) NULL,

    `txn_count` INT NOT NULL,

    `is_new_customer_flag` CHAR(1) NOT NULL,

    `is_high_value_flag` CHAR(1) NOT NULL,

    `policy_number` VARCHAR(30) NOT NULL,

    `folio_number` VARCHAR(30) NULL,

    `status` VARCHAR(20) NOT NULL,

    `src_created_at` DATETIME NOT NULL,

    `src_updated_at` DATETIME NOT NULL,

    `etl_run_id` VARCHAR(30) NOT NULL,

    `etl_load_ts_utc` DATETIME NOT NULL,

    PRIMARY KEY (`sales_sk`),

    UNIQUE KEY `uk_fact_sales_distributor_txn`
        (`distributor_txn_id`),

    UNIQUE KEY `uk_fact_sales_policy_number`
        (`policy_number`),

    CONSTRAINT `chk_fact_sales_gross`
        CHECK (`gross_amount` > 0),

    CONSTRAINT `chk_fact_sales_net`
        CHECK (`net_amount` >= 0),

    CONSTRAINT `chk_fact_sales_commission`
        CHECK (
            `commission_amount` IS NULL
            OR (
                `commission_amount` >= 0
                AND `commission_amount` <= `gross_amount`
            )
        ),

    CONSTRAINT `chk_fact_sales_tax`
        CHECK (`tax_amount` >= 0),

    CONSTRAINT `chk_fact_sales_discount`
        CHECK (`discount_amount` >= 0),

    CONSTRAINT `chk_fact_sales_commission_pct`
        CHECK (
            `commission_pct` IS NULL
            OR (
                `commission_pct` >= 0
                AND `commission_pct` <= 15
            )
        ),

    CONSTRAINT `chk_fact_sales_txn_count`
        CHECK (`txn_count` = 1),

    CONSTRAINT `chk_fact_sales_new_customer`
        CHECK (
            `is_new_customer_flag` IN ('Y','N')
        ),

    CONSTRAINT `chk_fact_sales_high_value`
        CHECK (
            `is_high_value_flag` IN ('Y','N')
        ),

   
    CONSTRAINT `chk_fact_sales_source_dates`
        CHECK (`src_updated_at` >= `src_created_at`)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;