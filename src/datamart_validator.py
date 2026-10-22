"""Data Mart Validator: validates dm_Distributor_Sales_Customer_360 in MySQL.   Checks: DM-001 .. DM-012"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import validators as v
from src.business_rules import family_of
from src.normalizer import blank_mask
from src.registry import qa_check
from src.results import Outcome

SET, MOD, DS, AREA = "datamart_validation", "Data Mart Validation", "dm_Distributor_Sales_Customer_360", "Target (data mart)"
ID = "distributor_txn_id"


def _reg(test_id, title, category, severity="High", area=AREA, extra=()):
    return qa_check(test_id, suite=SET, module=MOD, category=category, severity=severity, dataset=DS,
                    defect_area=area, title=title, requires=["db:dm", *extra])


@_reg("DM-001", "Mandatory (NOT NULL) data-mart columns are populated", "Completeness", "Critical")
def dm_mandatory(ctx):
    return v.mandatory(ctx.db_raw("dm"), ctx.schema("dm"), ID)


@_reg("DM-002", "Domains: status, product_family, product_category, flags, gender, kyc_status, segment hold valid values", "Domain", "High")
def dm_domains(ctx):
    raw, d = ctx.db_raw("dm"), ctx.rules["domains"]
    spec = [("status", d["dm_status"]), ("product_family", d["product_family"]), ("product_category", d["product_category"]),
            ("gender", d["gender"]), ("kyc_status", d["kyc_status"]), ("customer_segment", d["customer_segment"])]
    spec += [(f, d["yn"]) for f in ["is_new_customer_flag", "is_high_value_flag", "is_kyc_verified_flag", "is_ins_txn_flag", "is_mf_txn_flag"]]
    rules = [((~raw[c].isin(vals)) & ~blank_mask(raw[c]) if c in ("gender", "kyc_status", "customer_segment") else ~raw[c].isin(vals),
              f"{c} not in {vals}", [c]) for c, vals in spec]
    return v.multi_rule(raw, rules, ID)


@_reg("DM-003", "product_family / product_category are consistent with product_code and product_type_raw (family rules)", "Product family", "High")
def dm_family(ctx):
    raw, fr = ctx.db_raw("dm"), ctx.rules["family_rules"]
    fam = raw["product_code"].map(family_of)
    cat = fam.map(lambda f: fr.get(f, {}).get("category", "?"))
    type_ok = pd.Series([t in fr.get(f, {}).get("product_types", []) for t, f in zip(raw["product_type_raw"], fam)], index=raw.index)
    return v.multi_rule(raw, [
        (raw["product_family"] != fam, "product_family does not match product_code prefix", ["product_code", "product_family"]),
        (raw["product_category"] != cat, "product_category does not match family", ["product_code", "product_family", "product_category"]),
        (~type_ok, "product_type_raw invalid for family", ["product_code", "product_type_raw"]),
    ], ID)


@_reg("DM-004", "Value rules: gross>0, net>=0, 0<=commission<=gross, 0<=commission_pct<=15, txn_count=1, tax/discount>=0", "Business rule", "Critical")
def dm_values(ctx):
    t, raw, mx = ctx.db_typed("dm"), ctx.db_raw("dm"), ctx.thresholds["commission_pct_max"]
    df = raw[[ID]].assign(**{k: t[k] for k in ["gross_amount", "net_amount", "commission_amount", "commission_pct", "txn_count", "tax_amount", "discount_amount"]})
    return v.multi_rule(df, [
        (df.gross_amount <= 0, "gross_amount must be > 0", ["gross_amount"]),
        (df.net_amount < 0, "net_amount must be >= 0", ["net_amount"]),
        (df.commission_amount < 0, "commission_amount negative", ["commission_amount"]),
        (df.commission_amount > df.gross_amount, "commission_amount exceeds gross_amount", ["gross_amount", "commission_amount"]),
        ((df.commission_pct < 0) | (df.commission_pct > mx), f"commission_pct outside 0..{mx}", ["commission_pct"]),
        (df.txn_count.ne(1), "txn_count must be 1", ["txn_count"]),
        ((df.tax_amount < 0) | (df.discount_amount < 0), "tax/discount negative", ["tax_amount", "discount_amount"]),
    ], ID)


@_reg("DM-005", "Customer attributes are populated whenever customer_key is populated (no partial enrichment)", "Completeness", "High")
def dm_partial_enrichment(ctx):
    raw = ctx.db_raw("dm")
    has_key = ~blank_mask(raw["customer_key"])
    if not has_key.any():
        return Outcome.skip("BLOCKED: no data-mart row is linked to a customer, so enrichment completeness cannot be evaluated (see DM-007)")
    cols = ["first_name", "last_name", "gender", "date_of_birth", "email", "mobile", "kyc_status", "customer_segment", "customer_age"]
    sub = raw[has_key]
    return v.multi_rule(sub, [(blank_mask(sub[c]), f"{c} blank although customer_key populated", [c, "customer_key"]) for c in cols], ID, total=len(sub))


@_reg("DM-006", "customer_age is plausible and equals full years between date_of_birth and sale_date", "Derived value", "Medium")
def dm_age(ctx):
    raw, t = ctx.db_raw("dm"), ctx.db_typed("dm")
    has = t["date_of_birth"].notna()
    if not has.any():
        return Outcome.skip("BLOCKED: no data-mart row has date_of_birth, so customer_age cannot be evaluated (see DM-007)")
    sd, dob = t["sale_date"], t["date_of_birth"]
    exp = sd.dt.year - dob.dt.year - ((sd.dt.month < dob.dt.month) | ((sd.dt.month == dob.dt.month) & (sd.dt.day < dob.dt.day))).astype(int)
    lo, hi = ctx.thresholds["customer_age_min"], ctx.thresholds["customer_age_max"]
    df = raw[[ID, "date_of_birth", "sale_date", "customer_age"]].assign(expected_age=exp)[has]
    a = t.loc[has, "customer_age"]
    return v.multi_rule(df, [(a != df["expected_age"], "customer_age differs from recomputed age", ["customer_age", "expected_age"]),
                             ((a < lo) | (a > hi), f"customer_age outside {lo}..{hi}", ["customer_age"])], ID)


@_reg("DM-007", "Customer-360 enrichment: sales with a customer_id are linked to the Customer Master (customer_key/attributes populated)", "Referential integrity", "Critical",
      area="Mapping/Reference")
def dm_enrichment(ctx):
    """The purpose of the Customer-360 mart: every sale carrying a customer_id must receive customer attributes."""
    raw = ctx.db_raw("dm")
    needs = ~blank_mask(raw["customer_id"])
    missing = needs & blank_mask(raw["customer_key"])
    out = v.rows_outcome(raw, missing, ID, ["customer_id", "customer_key", "first_name", "kyc_status", "customer_segment"],
                         "customer_id present but no Customer Master record joined", total=int(needs.sum()))
    if out.failed is not None:
        out.message = (f"{int(missing.sum()):,} of {int(needs.sum()):,} data-mart rows ({100 * missing.mean() / needs.mean():.1f}% of rows that carry a customer_id) "
                       f"have NO customer attributes. Join key dim_Distributor_sales.customer_id (CUST...) never matches dim_Customer_Master.customer_id (CUC...). See REF-001")
    return out


@_reg("DM-008", "Audit/lineage columns populated and well-formed (fact_etl_run_id, dm_etl_run_id pattern, load timestamp)", "Lineage", "Medium")
def dm_audit(ctx):
    raw, t = ctx.db_raw("dm"), ctx.db_typed("dm")
    rx = ctx.rules["patterns"]["dm_etl_run_id"]
    return v.multi_rule(raw, [
        (blank_mask(raw["fact_etl_run_id"]), "fact_etl_run_id blank", ["fact_etl_run_id"]),
        (~raw["dm_etl_run_id"].str.match(rx), f"dm_etl_run_id does not match {rx}", ["dm_etl_run_id"]),
        (t["dm_load_ts_utc"].isna() | (t["dm_load_ts_utc"] > pd.Timestamp.utcnow().tz_localize(None)), "dm_load_ts_utc null or in the future", ["dm_load_ts_utc"]),
    ], ID)


@_reg("DM-009", "dm_sk is a contiguous sequence 1..N ordered by sales_sk", "Key integrity", "Medium")
def dm_sk(ctx):
    t, raw = ctx.db_typed("dm"), ctx.db_raw("dm")
    order = t.sort_values("sales_sk").reset_index()
    exp = pd.Series(np.arange(1, len(order) + 1), index=order["index"])
    df = raw[[ID, "sales_sk", "dm_sk"]].assign(expected_dm_sk=exp)
    return v.rows_outcome(df, t["dm_sk"] != df["expected_dm_sk"], ID, ["sales_sk", "dm_sk", "expected_dm_sk"], "dm_sk not sequential by sales_sk")


@_reg("DM-010", "Flags are consistent with their sources: is_ins/is_mf vs product_family, is_kyc_verified vs kyc_status, is_high_value vs gross", "Derived value", "High")
def dm_flags(ctx):
    raw, t = ctx.db_raw("dm"), ctx.db_typed("dm")
    thr = ctx.thresholds["high_value_gross_threshold"]
    return v.multi_rule(raw, [
        ((raw["is_ins_txn_flag"] == "Y") != (raw["product_family"] == "INS"), "is_ins_txn_flag inconsistent with product_family", ["is_ins_txn_flag", "product_family"]),
        ((raw["is_mf_txn_flag"] == "Y") != (raw["product_family"] == "MF"), "is_mf_txn_flag inconsistent with product_family", ["is_mf_txn_flag", "product_family"]),
        ((raw["is_kyc_verified_flag"] == "Y") != (raw["kyc_status"] == "VERIFIED"), "is_kyc_verified_flag inconsistent with kyc_status", ["is_kyc_verified_flag", "kyc_status"]),
        ((raw["is_high_value_flag"] == "Y") != (t["gross_amount"] >= thr), f"is_high_value_flag inconsistent with gross_amount >= {thr:,}", ["is_high_value_flag", "gross_amount"]),
    ], ID)


@_reg("DM-011", "sale_date equals sale_date_key; text values fit DDL lengths", "Format", "Medium")
def dm_dates_lengths(ctx):
    t, raw = ctx.db_typed("dm"), ctx.db_raw("dm")
    out = v.rows_outcome(raw.assign(_k=t["sale_date"].dt.strftime("%Y%m%d")), t["sale_date"].dt.strftime("%Y%m%d") != raw["sale_date_key"],
                         ID, ["sale_date", "sale_date_key"], "sale_date differs from sale_date_key")
    ln = v.lengths(raw, ctx.schema("dm"), ID)
    if out.failed is None and ln.failed is None:
        return Outcome(total=out.total, message="sale_date matches sale_date_key; all text values fit DDL lengths")
    return Outcome(total=out.total + ln.total, failed=pd.concat([x for x in (out.failed, ln.failed) if x is not None], ignore_index=True),
                   message="; ".join(m for m in (out.message if out.failed is not None else "", ln.message if ln.failed is not None else "") if m))


@_reg("DM-012", "Every data-mart record can be attributed to a customer (customer_id populated)", "Completeness", "High", area="Source data")
def dm_customer_id_populated(ctx):
    raw = ctx.db_raw("dm")
    return v.rows_outcome(raw, blank_mask(raw["customer_id"]), ID, ["policy_number", "customer_id", "customer_key"],
                          "No customer reference in data mart (blank customer_id in source)")
