"""Customer Validator module: Customer Master content (CUS-001..013) and customer
referential integrity of sales data against the master (REF-001..007).
"""
from __future__ import annotations

import pandas as pd

from src import validators as v
from src.normalizer import blank_mask
from src.registry import qa_check
from src.results import Outcome

SET = "customer_validation"
C_MOD, R_MOD = "Customer Master Validation", "Customer Reference Validation"
CUST = "Customer Master (TXT/CSV)"
ID = "customer_key"


# ============================ CUSTOMER MASTER ================================
@qa_check("CUS-001", suite=SET, module=C_MOD, category="Completeness", severity="Critical", dataset=CUST,
          defect_area="Customer Master", title="Mandatory (NOT NULL) customer fields are populated", requires=["cust"])
def cus_mandatory(ctx):
    return v.mandatory(ctx.raw("cust"), ctx.schema("cust"), ID)


@qa_check("CUS-002", suite=SET, module=C_MOD, category="Uniqueness", severity="Critical", dataset=CUST,
          defect_area="Customer Master", title="customer_key (primary key) is unique", requires=["cust"])
def cus_key_unique(ctx):
    return v.unique(ctx.raw("cust"), ID, ["customer_id"], "customer_key")


@qa_check("CUS-003", suite=SET, module=C_MOD, category="Uniqueness", severity="High", dataset=CUST,
          defect_area="Customer Master", title="policy_number is unique (DDL unique key)", requires=["cust"])
def cus_policy_unique(ctx):
    return v.unique(ctx.raw("cust"), "policy_number", [ID, "customer_id"], "policy_number")


@qa_check("CUS-004", suite=SET, module=C_MOD, category="Uniqueness", severity="High", dataset=CUST,
          defect_area="Customer Master", title="customer_id is unique (no duplicate customer records)", requires=["cust"])
def cus_id_unique(ctx):
    """customer_id is the business key used by the data-mart join; duplicates fan-out joins."""
    return v.unique(ctx.raw("cust"), "customer_id", [ID, "customer_pan", "first_name", "last_name", "date_of_birth"], "customer_id")


@qa_check("CUS-005", suite=SET, module=C_MOD, category="Consistency", severity="High", dataset=CUST,
          defect_area="Customer Master", title="Records sharing a customer_id do not carry conflicting identity attributes (PAN / DOB)",
          requires=["cust"])
def cus_dup_conflict(ctx):
    raw = ctx.raw("cust")
    dup = raw[raw.duplicated("customer_id", keep=False)]
    g = dup.groupby("customer_id").agg(records=(ID, "count"), distinct_pan=("customer_pan", "nunique"),
                                       distinct_dob=("date_of_birth", "nunique"),
                                       distinct_name=("first_name", "nunique")).reset_index()
    total = int(raw["customer_id"].nunique())
    bad = g[(g.distinct_pan > 1) | (g.distinct_dob > 1)].copy()
    if bad.empty:
        return Outcome(total=total, message="No customer_id maps to conflicting PAN/DOB")
    bad["failure_reason"] = "Same customer_id used for different people (conflicting PAN/DOB)"
    return Outcome(total=total, failed=bad, message=f"{len(bad):,} customer_id values shared by records with conflicting PAN/DOB")


@qa_check("CUS-006", suite=SET, module=C_MOD, category="Format", severity="Medium", dataset=CUST,
          defect_area="Customer Master", title="customer_id follows format CUC + digits", requires=["cust"])
def cus_id_format(ctx):
    return v.pattern(ctx.raw("cust"), "customer_id", ctx.rules["patterns"]["master_customer_id"], ID, allow_blank=False)


@qa_check("CUS-007", suite=SET, module=C_MOD, category="Domain", severity="High", dataset=CUST,
          defect_area="Customer Master", title="gender, kyc_status, customer_segment, active_flag hold valid values", requires=["cust"])
def cus_domains(ctx):
    raw, d = ctx.raw("cust"), ctx.rules["domains"]
    spec = [("gender", d["gender"]), ("kyc_status", d["kyc_status"]), ("customer_segment", d["customer_segment"]), ("active_flag", d["yn"])]
    rules = [(~raw[c].isin(vals), f"{c} not in {vals}", [c]) for c, vals in spec]
    return v.multi_rule(raw, rules, ID)


@qa_check("CUS-008", suite=SET, module=C_MOD, category="Format", severity="Medium", dataset=CUST,
          defect_area="Customer Master", title="email, mobile, pincode and PAN have valid formats", requires=["cust"])
def cus_formats(ctx):
    raw, p = ctx.raw("cust"), ctx.rules["patterns"]
    spec = [("email", p["email"]), ("mobile", p["mobile"]), ("pincode", p["pincode"]), ("customer_pan", p["pan"])]
    rules = [(~raw[c].str.strip().str.match(rx) & ~blank_mask(raw[c]), f"{c} has invalid format", [c]) for c, rx in spec]
    return v.multi_rule(raw, rules, ID)


@qa_check("CUS-009", suite=SET, module=C_MOD, category="Data type", severity="High", dataset=CUST,
          defect_area="Customer Master", title="Numeric and date fields are valid", requires=["cust"])
def cus_types(ctx):
    cols = [c["name"] for c in ctx.schema("cust")["columns"] if c["type"] in ("int", "decimal", "date", "datetime")]
    return v.valid_types(ctx.raw("cust"), ctx.invalid("cust"), cols, ID, "number/date")


@qa_check("CUS-010", suite=SET, module=C_MOD, category="Business rule", severity="Medium", dataset=CUST,
          defect_area="Customer Master", title="annual_income >= 0; DOB not in future; customer was an adult at onboarding", requires=["cust"])
def cus_business(ctx):
    raw, t = ctx.raw("cust"), ctx.typed("cust")
    min_age = ctx.thresholds["min_customer_age_at_onboarding"]
    df = raw.assign(_inc=t["annual_income"], _dob=t["date_of_birth"], _on=t["onboarded_on"])
    age = (df["_on"] - df["_dob"]).dt.days / 365.25
    return v.multi_rule(df, [
        (df["_inc"] < 0, "annual_income is negative", ["annual_income"]),
        (df["_dob"] > pd.Timestamp.now(), "date_of_birth is in the future", ["date_of_birth"]),
        (df["_dob"] > df["_on"], "date_of_birth after onboarded_on", ["date_of_birth", "onboarded_on"]),
        (age < min_age, f"customer younger than {min_age} at onboarding", ["date_of_birth", "onboarded_on"]),
    ], ID)


@qa_check("CUS-011", suite=SET, module=C_MOD, category="Temporal", severity="Medium", dataset=CUST,
          defect_area="Customer Master", title="updated_at >= created_at", requires=["cust"])
def cus_temporal(ctx):
    raw, t = ctx.raw("cust"), ctx.typed("cust")
    df = raw.assign(_c=t["created_at"], _u=t["updated_at"])
    return v.rows_outcome(df, df["_u"] < df["_c"], ID, ["created_at", "updated_at"], "updated_at earlier than created_at")


@qa_check("CUS-012", suite=SET, module=C_MOD, category="Data truncation", severity="Medium", dataset=CUST,
          defect_area="Customer Master", title="Text values fit DDL column lengths", requires=["cust"])
def cus_lengths(ctx):
    return v.lengths(ctx.raw("cust"), ctx.schema("cust"), ID)


@qa_check("CUS-013", suite=SET, module=C_MOD, category="Format", severity="Low", dataset=CUST,
          defect_area="Customer Master", title="No leading/trailing whitespace in values", requires=["cust"])
def cus_whitespace(ctx):
    return v.whitespace(ctx.raw("cust"), ID)


# ====================== CUSTOMER REFERENCE VALIDATION ========================
@qa_check("REF-001", suite=SET, module=R_MOD, category="Referential integrity", severity="Critical",
          dataset="Distributor Sales -> Customer Master", defect_area="Mapping/Reference",
          title="Every distributor customer_id exists in Customer Master (customer_id)", requires=["dist", "cust"])
def ref_dist_customer(ctx):
    """Data-mart join key: dim_Distributor_sales.customer_id = dim_Customer_Master.customer_id."""
    d, c = ctx.raw("dist"), ctx.raw("cust")
    populated = ~blank_mask(d["customer_id"])
    orphan = populated & ~d["customer_id"].isin(set(c["customer_id"]))
    out = v.rows_outcome(d, orphan, "distributor_txn_id", ["customer_id", "policy_number"],
                         "customer_id not found in Customer Master", total=int(populated.sum()))
    if out.failed is not None:
        out.message = (f"{int(orphan.sum()):,} of {int(populated.sum()):,} sales ({100*orphan.sum()/populated.sum():.1f}%) reference a "
                       f"customer_id absent from Customer Master; {d.loc[orphan,'customer_id'].nunique():,} distinct ids. "
                       f"Sample id '{d.loc[orphan,'customer_id'].iloc[0]}' vs master format '{c['customer_id'].iloc[0]}'")
    return out


@qa_check("REF-002", suite=SET, module=R_MOD, category="Referential integrity", severity="Critical",
          dataset="Fact Sales -> Customer Master", defect_area="Mapping/Reference",
          title="Every Fact_Sales customer_key exists in Customer Master (customer_key)", requires=["fact", "cust"])
def ref_fact_customer(ctx):
    f, c = ctx.raw("fact"), ctx.raw("cust")
    populated = ~blank_mask(f["customer_key"])
    orphan = populated & ~f["customer_key"].isin(set(c["customer_key"]))
    out = v.rows_outcome(f, orphan, "sales_sk", ["distributor_txn_id", "customer_key"],
                         "customer_key not found in Customer Master", total=int(populated.sum()))
    if out.failed is not None:
        ks = pd.to_numeric(f.loc[orphan, "customer_key"])
        out.message = (f"{int(orphan.sum()):,} of {int(populated.sum()):,} fact rows reference a customer_key absent from Customer Master "
                       f"(fact keys {ks.min():,.0f}-{ks.max():,.0f}; master keys {pd.to_numeric(c['customer_key']).min():,.0f}-"
                       f"{pd.to_numeric(c['customer_key']).max():,.0f})")
    return out


@qa_check("REF-003", suite=SET, module=R_MOD, category="Consistency", severity="High",
          dataset="Distributor Sales vs Fact Sales", defect_area="Mapping/Reference",
          title="customer_id (distributor) <-> customer_key (fact) mapping is one-to-one", requires=["dist", "fact"])
def ref_mapping_1to1(ctx):
    d, f = ctx.raw("dist"), ctx.raw("fact")
    m = d[["distributor_txn_id", "customer_id"]].merge(f[["distributor_txn_id", "customer_key"]], on="distributor_txn_id")
    m = m[(m.customer_id != "") & (m.customer_key != "")]
    a = m.groupby("customer_id")["customer_key"].nunique()
    b = m.groupby("customer_key")["customer_id"].nunique()
    bad = pd.concat([a[a > 1].rename("n").reset_index().assign(failure_reason="customer_id maps to several customer_key"),
                     b[b > 1].rename("n").reset_index().assign(failure_reason="customer_key maps to several customer_id")],
                    ignore_index=True)
    total = int(m["customer_id"].nunique())
    if bad.empty:
        return Outcome(total=total, message=f"{total:,} customer_id values map 1:1 to customer_key")
    return Outcome(total=total, failed=bad, message=f"{len(bad):,} inconsistent customer mappings")


@qa_check("REF-004", suite=SET, module=R_MOD, category="Consistency", severity="High",
          dataset="Distributor Sales vs Fact Sales", defect_area="Mapping/Reference",
          title="Blank customer_id in source <=> blank customer_key in Fact_Sales", requires=["dist", "fact"])
def ref_null_consistency(ctx):
    d, f = ctx.raw("dist"), ctx.raw("fact")
    m = d[["distributor_txn_id", "customer_id"]].merge(f[["distributor_txn_id", "customer_key"]], on="distributor_txn_id")
    bad = blank_mask(m["customer_id"]) != blank_mask(m["customer_key"])
    return v.rows_outcome(m, bad, "distributor_txn_id", ["customer_id", "customer_key"],
                          "customer reference populated in only one of source / fact")


@qa_check("REF-005", suite=SET, module=R_MOD, category="Consistency", severity="Medium",
          dataset="Distributor Sales vs Customer Master", defect_area="Customer Master",
          title="customer_pan agrees between Distributor Sales and Customer Master (linked by policy_number) [inferred link]",
          requires=["dist", "cust"])
def ref_pan_consistency(ctx):
    """INF: Customer Master.policy_number == Distributor.policy_number for every record, so PAN must agree."""
    d, c = ctx.raw("dist"), ctx.raw("cust")
    m = d[["distributor_txn_id", "policy_number", "customer_pan"]].merge(
        c[["policy_number", "customer_key", "customer_pan"]], on="policy_number", suffixes=("_dist", "_master"))
    m = m[(m.customer_pan_dist != "") & (m.customer_pan_master != "")]
    return v.rows_outcome(m, m.customer_pan_dist != m.customer_pan_master, "distributor_txn_id",
                          ["policy_number", "customer_pan_dist", "customer_pan_master"], "PAN differs between source and Customer Master")


@qa_check("REF-006", suite=SET, module=R_MOD, category="Business rule", severity="Medium",
          dataset="Distributor Sales -> Customer Master", defect_area="Customer Master",
          title="Sales do not reference inactive (active_flag=N) or KYC-REJECTED customers", requires=["dist", "cust"])
def ref_inactive_customer(ctx):
    d, c = ctx.raw("dist"), ctx.raw("cust")
    c1 = c.drop_duplicates("customer_id")
    m = d[["distributor_txn_id", "customer_id", "status"]].merge(c1[["customer_id", "active_flag", "kyc_status"]], on="customer_id")
    if m.empty:
        return Outcome.skip("BLOCKED: no sale resolves to a Customer Master record, so customer status cannot be evaluated (see REF-001)")
    m = m[m.status == "APPROVED"]
    return v.multi_rule(m, [(m.active_flag == "N", "Approved sale for inactive customer", ["customer_id", "active_flag"]),
                            (m.kyc_status == "REJECTED", "Approved sale for KYC-rejected customer", ["customer_id", "kyc_status"])],
                        "distributor_txn_id")


@qa_check("REF-007", suite=SET, module=R_MOD, category="Referential integrity", severity="Medium",
          dataset="Customer Master -> Distributor Sales", defect_area="Customer Master",
          title="Every Customer Master policy_number exists in Distributor Sales (no orphan customers)", requires=["dist", "cust"])
def ref_orphan_customers(ctx):
    d, c = ctx.raw("dist"), ctx.raw("cust")
    return v.rows_outcome(c, ~c["policy_number"].isin(set(d["policy_number"])), ID, ["customer_id", "policy_number"],
                          "Customer policy_number has no sales record")
