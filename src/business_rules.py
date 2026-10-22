"""Business Rules module: calculations (CAL), product & family rules (PRD), key<->code mappings (MAP), temporal (BR).

Rule provenance (DOC vs INF) is documented in config/business_rules.json -> rule_status.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from src import validators as v
from src.normalizer import blank_mask
from src.registry import qa_check
from src.results import Outcome

SET = "business_rules"
CAL, PRD, MAP, BR = "Monetary Calculation Validation", "Product & Product Family Validation", "Key/Code Mapping Validation", "Business Rule Validation"
FACT = "Fact Sales (CSV)"


def _fact_dist(ctx) -> pd.DataFrame:
    """Raw string frame: Fact_Sales joined to Distributor Sales on transaction id."""
    f, d = ctx.raw("fact"), ctx.raw("dist")
    return f.merge(d[["distributor_txn_id", "product_code", "product_name_raw", "product_type_raw", "distributor_code", "region_code"]],
                   on="distributor_txn_id", how="inner")


def family_of(code: str) -> str:
    c = (code or "").upper()
    return "INS" if c.startswith("INS") else "MF" if c.startswith("MF") else "UNKNOWN"


# =============================== CALCULATIONS ================================
def _net_formula(df: pd.DataFrame, t: pd.DataFrame, id_col: str, tol: float) -> Outcome:
    exp = (t["gross_amount"] - t["commission_amount"]).round(2)
    ev = df[[id_col]].assign(gross_amount=t["gross_amount"], commission_amount=t["commission_amount"],
                             net_amount=t["net_amount"], expected_net=exp, difference=(t["net_amount"] - exp).round(2))
    return v.rows_outcome(ev, (ev["difference"].abs() > tol) | t["net_amount"].isna(), id_col,
                          ["gross_amount", "commission_amount", "net_amount", "expected_net", "difference"],
                          "net_amount <> gross_amount - commission_amount")


@qa_check("CAL-001", suite=SET, module=CAL, category="Calculation", severity="Critical", dataset=FACT, defect_area="Source data",
          title="net_amount = gross_amount - commission_amount [inferred rule]", requires=["fact"])
def cal_net_fact(ctx):
    return _net_formula(ctx.raw("fact"), ctx.typed("fact"), "sales_sk", ctx.thresholds["amount_tolerance"])


@qa_check("CAL-002", suite=SET, module=CAL, category="Calculation", severity="High", dataset=FACT, defect_area="Source data",
          title="commission_pct = commission_amount / gross_amount x 100 (3 d.p.)", requires=["fact"])
def cal_comm_pct(ctx):
    t = ctx.typed("fact")
    exp = (t["commission_amount"] / t["gross_amount"] * 100)
    ev = ctx.raw("fact")[["sales_sk"]].assign(gross_amount=t["gross_amount"], commission_amount=t["commission_amount"],
                                              commission_pct=t["commission_pct"], expected_pct=exp.round(3))
    bad = (t["commission_pct"] - exp).abs() > ctx.thresholds["commission_pct_tolerance"]
    return v.rows_outcome(ev, bad & t["commission_pct"].notna(), "sales_sk", ["gross_amount", "commission_amount", "commission_pct", "expected_pct"],
                          "commission_pct inconsistent with commission_amount / gross_amount")


@qa_check("CAL-003", suite=SET, module=CAL, category="Calculation", severity="High", dataset=FACT, defect_area="Source data",
          title="Mutual-fund rows: units_allocated x nav_at_purchase ~= gross_amount [inferred rule]", requires=["fact"])
def cal_units_nav(ctx):
    t = ctx.typed("fact")
    mf = t["units_allocated"].notna() | t["nav_at_purchase"].notna()
    val = t["units_allocated"].astype(float) * t["nav_at_purchase"].astype(float)
    ev = ctx.raw("fact")[["sales_sk"]].assign(units_allocated=t["units_allocated"], nav_at_purchase=t["nav_at_purchase"],
                                              gross_amount=t["gross_amount"], units_x_nav=val.round(2))
    bad = mf & (((val - t["gross_amount"]).abs() > ctx.thresholds["units_x_nav_tolerance_abs"]) | val.isna())
    return v.rows_outcome(ev, bad, "sales_sk", ["units_allocated", "nav_at_purchase", "gross_amount", "units_x_nav"],
                          "units x NAV differs from gross_amount beyond tolerance", total=int(mf.sum()))


@qa_check("CAL-004", suite=SET, module=CAL, category="Calculation", severity="Medium", dataset=FACT, defect_area="Source data",
          title="Insurance rows: premium_amount <= gross_amount and sum_assured > premium_amount", requires=["fact"])
def cal_insurance(ctx):
    t = ctx.typed("fact")
    ins = t["premium_amount"].notna() | t["sum_assured"].notna()
    ev = ctx.raw("fact")[["sales_sk"]].assign(gross_amount=t["gross_amount"], premium_amount=t["premium_amount"], sum_assured=t["sum_assured"])
    return v.multi_rule(ev[ins], [(t.loc[ins, "premium_amount"] > t.loc[ins, "gross_amount"], "premium_amount exceeds gross_amount", ["gross_amount", "premium_amount"]),
                                  (t.loc[ins, "sum_assured"] <= t.loc[ins, "premium_amount"], "sum_assured not greater than premium_amount", ["premium_amount", "sum_assured"])],
                        "sales_sk", total=int(ins.sum()))


@qa_check("CAL-005", suite=SET, module=CAL, category="Rounding / precision", severity="Medium", dataset="Distributor + Fact files", defect_area="Source data",
          title="Decimal precision does not exceed DDL scale (no silent rounding on load)", requires=["dist", "fact"])
def cal_precision(ctx):
    rows, total = [], 0
    for key, idc in (("dist", "distributor_txn_id"), ("fact", "sales_sk")):
        raw = ctx.raw(key)
        for col in ctx.schema(key)["columns"]:
            if col["type"] == "decimal":
                total += len(raw)
                rx = rf"^-?\d+(\.\d{{0,{col['scale']}}})?$"
                s = raw[col["name"]].str.strip()
                bad = (s != "") & ~s.str.match(rx)
                if bad.any():
                    e = raw.loc[bad, [idc, col["name"]]].rename(columns={col["name"]: "value"})
                    e["dataset"], e["column"], e["failure_reason"] = key, col["name"], f"More than {col['scale']} decimal places"
                    rows.append(e)
    if rows:
        ev = pd.concat(rows, ignore_index=True)
        return Outcome(total=total, failed=ev, message=f"{len(ev):,} value(s) exceed DDL decimal scale")
    return Outcome(total=total, message="All decimal values fit their DDL scale")


@qa_check("CAL-006", suite=SET, module=CAL, category="Derived flag", severity="Medium", dataset=FACT, defect_area="Source data",
          title="is_high_value_flag = 'Y' exactly when gross_amount >= threshold [inferred rule]", requires=["fact"])
def cal_high_value(ctx):
    t, raw = ctx.typed("fact"), ctx.raw("fact")
    thr = ctx.thresholds["high_value_gross_threshold"]
    exp = np.where(t["gross_amount"] >= thr, "Y", "N")
    df = raw[["sales_sk", "gross_amount", "is_high_value_flag"]].assign(expected_flag=exp)
    return v.rows_outcome(df, df["is_high_value_flag"] != df["expected_flag"], "sales_sk", ["gross_amount", "is_high_value_flag", "expected_flag"],
                          f"is_high_value_flag inconsistent with gross_amount >= {thr:,}")


@qa_check("CAL-007", suite=SET, module=CAL, category="Calculation", severity="Critical", dataset="Data mart", defect_area="Target (data mart)",
          title="Data mart: net_amount = gross_amount - commission_amount", requires=["db:dm"])
def cal_net_dm(ctx):
    return _net_formula(ctx.db_raw("dm"), ctx.db_typed("dm"), "distributor_txn_id", ctx.thresholds["amount_tolerance"])


@qa_check("CAL-008", suite=SET, module=CAL, category="Calculation", severity="High", dataset="Data mart", defect_area="Target (data mart)",
          title="Data mart: commission_pct consistent with commission_amount / gross_amount", requires=["db:dm"])
def cal_comm_pct_dm(ctx):
    t = ctx.db_typed("dm")
    exp = t["commission_amount"] / t["gross_amount"] * 100
    ev = ctx.db_raw("dm")[["distributor_txn_id"]].assign(commission_pct=t["commission_pct"], expected_pct=exp.round(3))
    bad = ((t["commission_pct"] - exp).abs() > ctx.thresholds["commission_pct_tolerance"]) & t["commission_pct"].notna()
    return v.rows_outcome(ev, bad, "distributor_txn_id", ["commission_pct", "expected_pct"], "commission_pct inconsistent")


# =========================== PRODUCT & PRODUCT FAMILY ========================
@qa_check("PRD-001", suite=SET, module=PRD, category="Product family", severity="High", dataset="Distributor Sales (JSON)", defect_area="Source data",
          title="product_code prefix identifies a known family (unknown prefixes would silently default to MF in the data mart)", requires=["dist"])
def prd_prefix(ctx):
    d = ctx.raw("dist")
    fam = d["product_code"].map(family_of)
    return v.rows_outcome(d.assign(derived_family=fam), fam == "UNKNOWN", "distributor_txn_id", ["product_code", "derived_family"],
                          "product_code prefix is neither MF nor INS")


@qa_check("PRD-002", suite=SET, module=PRD, category="Product family", severity="High", dataset="Distributor Sales (JSON)", defect_area="Source data",
          title="Product / product-family combination valid: product_type_raw belongs to the family given by product_code", requires=["dist"])
def prd_type_family(ctx):
    d, fr = ctx.raw("dist"), ctx.rules["family_rules"]
    fam = d["product_code"].map(family_of)
    ok = pd.Series([t in fr.get(f, {}).get("product_types", []) for t, f in zip(d["product_type_raw"], fam)], index=d.index)
    return v.rows_outcome(d.assign(derived_family=fam), ~ok, "distributor_txn_id", ["product_code", "product_type_raw", "derived_family"],
                          "product_type_raw is inconsistent with product family")


@qa_check("PRD-003", suite=SET, module=PRD, category="Product family", severity="High", dataset="Fact + Distributor", defect_area="Source data",
          title="Family-specific fields: MF has units/NAV/folio and no premium/sum assured; INS the reverse [inferred rule]", requires=["dist", "fact"])
def prd_family_fields(ctx):
    j, fr = _fact_dist(ctx), ctx.rules["family_rules"]
    j["family"] = j["product_code"].map(family_of)
    rules = []
    for fam, spec in fr.items():
        sel = j["family"] == fam
        for col in spec["required_fields"]:
            rules.append((sel & blank_mask(j[col]), f"{fam}: required field {col} is blank", ["product_code", col]))
        for col in spec["forbidden_fields"]:
            rules.append((sel & ~blank_mask(j[col]), f"{fam}: field {col} must be blank", ["product_code", col]))
    return v.multi_rule(j, rules, "sales_sk", total=len(j))


@qa_check("PRD-004", suite=SET, module=PRD, category="Mapping consistency", severity="High", dataset="Fact + Distributor", defect_area="Mapping/Reference",
          title="product_key <-> product_code is one-to-one", requires=["dist", "fact"])
def prd_key_code(ctx):
    return _one_to_one(_fact_dist(ctx), "product_key", "product_code")


@qa_check("PRD-005", suite=SET, module=PRD, category="Mapping consistency", severity="Medium", dataset="Distributor Sales (JSON)", defect_area="Source data",
          title="Each product_code carries exactly one product_name_raw and one product_type_raw", requires=["dist"])
def prd_name_code(ctx):
    d = ctx.raw("dist")
    g = d.groupby("product_code").agg(names=("product_name_raw", "nunique"), types=("product_type_raw", "nunique")).reset_index()
    bad = g[(g.names > 1) | (g.types > 1)]
    if bad.empty:
        return Outcome(total=len(g), message=f"{len(g)} product codes each map to one name and one type")
    return Outcome(total=len(g), failed=bad.assign(failure_reason="product_code has multiple names/types"), message=f"{len(bad)} product codes inconsistent")


# ============================ KEY <-> CODE MAPPING ===========================
def _one_to_one(df: pd.DataFrame, key_col: str, code_col: str) -> Outcome:
    m = df[(df[key_col] != "") & (df[code_col] != "")]
    a = m.groupby(key_col)[code_col].nunique()
    b = m.groupby(code_col)[key_col].nunique()
    bad = pd.concat([a[a > 1].rename("distinct_codes").reset_index().assign(failure_reason=f"{key_col} maps to several {code_col}"),
                     b[b > 1].rename("distinct_keys").reset_index().assign(failure_reason=f"{code_col} maps to several {key_col}")], ignore_index=True)
    total = int(m[key_col].nunique())
    if bad.empty:
        return Outcome(total=total, message=f"{total} {key_col} values map 1:1 to {code_col}")
    return Outcome(total=total, failed=bad, message=f"{len(bad)} inconsistent {key_col}/{code_col} mappings")


@qa_check("MAP-001", suite=SET, module=MAP, category="Mapping consistency", severity="High", dataset="Fact + Distributor", defect_area="Mapping/Reference",
          title="region_key <-> region_code is one-to-one", requires=["dist", "fact"])
def map_region(ctx):
    return _one_to_one(_fact_dist(ctx), "region_key", "region_code")


@qa_check("MAP-002", suite=SET, module=MAP, category="Completeness", severity="High", dataset="Fact + Distributor", defect_area="Source data",
          title="region_code is populated for every record that has a region_key (key resolves to a code)", requires=["dist", "fact"])
def map_region_populated(ctx):
    j = _fact_dist(ctx)
    out = v.rows_outcome(j, blank_mask(j["region_code"]), "sales_sk", ["distributor_txn_id", "region_key", "region_code"],
                         "region_key present but region_code blank in Distributor Sales")
    if out.failed is not None:
        out.message += f"; blanks occur only for region_key in {sorted(j.loc[blank_mask(j['region_code']), 'region_key'].unique())}"
    return out


@qa_check("MAP-003", suite=SET, module=MAP, category="Mapping consistency", severity="High", dataset="Fact + Distributor", defect_area="Mapping/Reference",
          title="distributor_key <-> distributor_code is one-to-one", requires=["dist", "fact"])
def map_distributor(ctx):
    return _one_to_one(_fact_dist(ctx), "distributor_key", "distributor_code")


# ================================ TEMPORAL ===================================
@qa_check("BR-001", suite=SET, module=BR, category="Temporal", severity="Medium", dataset="Distributor Sales (JSON)", defect_area="Source data",
          title="sale_date equals the calendar date of created_at [inferred rule]", requires=["dist"])
def br_sale_date_created(ctx):
    t, raw = ctx.typed("dist"), ctx.raw("dist")
    df = raw[["distributor_txn_id", "sale_date", "created_at"]]
    return v.rows_outcome(df, t["sale_date"] != t["created_at"].dt.normalize(), "distributor_txn_id", ["sale_date", "created_at"],
                          "sale_date differs from date of created_at (temporal drift)")


@qa_check("BR-002", suite=SET, module=BR, category="Temporal", severity="High", dataset="Distributor vs Fact", defect_area="Source data",
          title="Fact sale_date_key equals Distributor sale_date (no date drift between systems)", requires=["dist", "fact"])
def br_date_key(ctx):
    d, f = ctx.typed("dist"), ctx.typed("fact")
    m = ctx.raw("dist")[["distributor_txn_id", "sale_date"]].assign(_d=d["sale_date"].dt.strftime("%Y%m%d")).merge(
        ctx.raw("fact")[["distributor_txn_id", "sale_date_key"]], on="distributor_txn_id")
    return v.rows_outcome(m, m["_d"] != m["sale_date_key"].str.strip(), "distributor_txn_id", ["sale_date", "sale_date_key"],
                          "sale_date_key does not match sale_date")
