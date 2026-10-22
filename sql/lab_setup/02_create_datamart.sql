USE python_project2;

-- ============================================================
-- TARGET DATA MART TABLE
-- Object: dm_Distributor_Sales_Customer_360
-- MySQL 8.0 compatible version
-- ============================================================

DROP TABLE IF EXISTS dm_Distributor_Sales_Customer_360;

CREATE TABLE dm_Distributor_Sales_Customer_360 (

    -- A) Data Mart surrogate key
    dm_sk BIGINT NOT NULL,

    -- B) Business keys
    sales_sk BIGINT NOT NULL,
    distributor_txn_id VARCHAR(25) NOT NULL,
    policy_number VARCHAR(30) NOT NULL,
    customer_key INT NULL,
    customer_id VARCHAR(15) NULL,

    -- C) Distributor attributes
    sale_date DATE NOT NULL,
    sale_date_key INT NOT NULL,
    distributor_code VARCHAR(20) NOT NULL,
    distributor_name VARCHAR(150) NULL,
    product_code VARCHAR(30) NOT NULL,
    product_name_raw VARCHAR(200) NULL,
    product_type_raw VARCHAR(50) NOT NULL,
    product_family VARCHAR(10) NOT NULL,
    product_category VARCHAR(20) NOT NULL,
    folio_number VARCHAR(30) NULL,
    region_code VARCHAR(20) NULL,
    region_key INT NOT NULL,
    status VARCHAR(20) NOT NULL,

    -- D) Customer attributes
    customer_pan VARCHAR(10) NULL,
    first_name VARCHAR(50) NULL,
    last_name VARCHAR(50) NULL,
    gender CHAR(1) NULL,
    date_of_birth DATE NULL,
    customer_age INT NULL,
    email VARCHAR(100) NULL,
    mobile VARCHAR(15) NULL,
    city VARCHAR(50) NULL,
    state VARCHAR(50) NULL,
    pincode VARCHAR(10) NULL,
    country VARCHAR(50) NULL,
    kyc_status VARCHAR(20) NULL,
    customer_segment VARCHAR(20) NULL,
    annual_income DECIMAL(15,2) NULL,
    customer_onboarded_on DATE NULL,
    customer_active_flag CHAR(1) NULL,

    -- E) Fact metrics
    gross_amount DECIMAL(15,2) NOT NULL,
    net_amount DECIMAL(15,2) NOT NULL,
    commission_amount DECIMAL(15,2) NULL,
    tax_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    discount_amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    premium_amount DECIMAL(15,2) NULL,
    sum_assured DECIMAL(15,2) NULL,
    units_allocated DECIMAL(15,4) NULL,
    nav_at_purchase DECIMAL(15,4) NULL,
    commission_pct DECIMAL(6,3) NULL,
    txn_count INT NOT NULL DEFAULT 1,

    -- F) Flags
    is_new_customer_flag CHAR(1) NOT NULL DEFAULT 'N',
    is_high_value_flag CHAR(1) NOT NULL DEFAULT 'N',
    is_kyc_verified_flag CHAR(1) NOT NULL DEFAULT 'N',
    is_ins_txn_flag CHAR(1) NOT NULL DEFAULT 'N',
    is_mf_txn_flag CHAR(1) NOT NULL DEFAULT 'N',

    -- G) Audit / lineage
    src_created_at DATETIME NOT NULL,
    src_updated_at DATETIME NOT NULL,
    fact_etl_run_id VARCHAR(30) NOT NULL,
    dm_etl_run_id VARCHAR(30) NOT NULL,
    dm_load_ts_utc DATETIME NOT NULL,

    -- H) Constraints
    CONSTRAINT PK_dm_DSC360
        PRIMARY KEY (dm_sk),

    CONSTRAINT UQ_dm_DSC360_SalesSK
        UNIQUE (sales_sk),

    CONSTRAINT UQ_dm_DSC360_TxnId
        UNIQUE (distributor_txn_id),

    CONSTRAINT UQ_dm_DSC360_PolicyNum
        UNIQUE (policy_number),

    CONSTRAINT FK_dm_DSC360_Fact
        FOREIGN KEY (sales_sk)
        REFERENCES Fact_Sales(sales_sk),

    CONSTRAINT FK_dm_DSC360_Dim1_Txn
        FOREIGN KEY (distributor_txn_id)
        REFERENCES dim_Distributor_sales(distributor_txn_id),

    CONSTRAINT FK_dm_DSC360_Dim1_Policy
        FOREIGN KEY (policy_number)
        REFERENCES dim_Distributor_sales(policy_number),

    CONSTRAINT FK_dm_DSC360_Dim2_Customer
        FOREIGN KEY (customer_key)
        REFERENCES dim_Customer_Master(customer_key),

    CONSTRAINT CK_dm_DSC360_GrossPositive
        CHECK (gross_amount > 0),

    CONSTRAINT CK_dm_DSC360_CommCap
        CHECK (
            commission_amount IS NULL
            OR commission_amount <= gross_amount
        ),

    CONSTRAINT CK_dm_DSC360_CommPct
        CHECK (
            commission_pct IS NULL
            OR commission_pct BETWEEN 0 AND 15
        ),

    CONSTRAINT CK_dm_DSC360_Status
        CHECK (status = 'APPROVED'),

    CONSTRAINT CK_dm_DSC360_Family
        CHECK (product_family IN ('MF','INS')),

    CONSTRAINT CK_dm_DSC360_Category
        CHECK (
            product_category IN ('MUTUAL_FUND','INSURANCE')
        ),

    CONSTRAINT CK_dm_DSC360_Gender
        CHECK (
            gender IS NULL
            OR gender IN ('M','F','O')
        ),

    CONSTRAINT CK_dm_DSC360_KYC
        CHECK (
            kyc_status IS NULL
            OR kyc_status IN ('VERIFIED','PENDING','REJECTED')
        ),

    CONSTRAINT CK_dm_DSC360_Segment
        CHECK (
            customer_segment IS NULL
            OR customer_segment IN
               ('RETAIL','HNI','PREMIUM','CORPORATE')
        )

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IX_dm_DSC360_SaleDate
    ON dm_Distributor_Sales_Customer_360(sale_date);

CREATE INDEX IX_dm_DSC360_SaleDateKey
    ON dm_Distributor_Sales_Customer_360(sale_date_key);

CREATE INDEX IX_dm_DSC360_Distributor
    ON dm_Distributor_Sales_Customer_360(distributor_code);

CREATE INDEX IX_dm_DSC360_Product
    ON dm_Distributor_Sales_Customer_360(product_code);

CREATE INDEX IX_dm_DSC360_ProdCategory
    ON dm_Distributor_Sales_Customer_360(product_category);

CREATE INDEX IX_dm_DSC360_Region
    ON dm_Distributor_Sales_Customer_360(region_code);

CREATE INDEX IX_dm_DSC360_Segment
    ON dm_Distributor_Sales_Customer_360(customer_segment);

CREATE INDEX IX_dm_DSC360_KYC
    ON dm_Distributor_Sales_Customer_360(kyc_status);

CREATE INDEX IX_dm_DSC360_HighValue
    ON dm_Distributor_Sales_Customer_360(is_high_value_flag);