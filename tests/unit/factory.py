"""Synthetic, internally-consistent datasets for framework self-tests (all strings, like the file readers produce)."""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta

import pandas as pd

PRODUCTS = [("MF_EQ_001", "Equity Fund Alpha", "Equity Fund", 1, "MF"), ("MF_DEBT_002", "Debt Fund Beta", "Debt Fund", 2, "MF"),
            ("INS_TERM_003", "Term Cover", "INS", 3, "INS"), ("INS_ULIP_004", "ULIP Plan", "ULIP", 4, "INS")]
DISTRIBUTORS = [("DIST_A", "Dist A", 1), ("DIST_B", "Dist B", 2), ("DIST_C", "Dist C", 3)]
REGIONS = [("NORTH", 1), ("SOUTH", 2), ("EAST", 3)]


def mdy(d) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def make_clean(n: int = 60):
    dist, fact, cust = [], [], []
    for i in range(1, n + 1):
        code, pname, ptype, pkey, fam = PRODUCTS[i % 4]
        dcode, dname, dkey = DISTRIBUTORS[i % 3]
        rcode, rkey = REGIONS[i % 3]
        sale = date(2026, 1, 1) + timedelta(days=i % 28)
        created = datetime(sale.year, sale.month, sale.day, 8, i % 60)
        updated = created + timedelta(hours=1)
        gross = round(1000 + i * 3333.37, 2)
        comm = round(gross * 0.04, 2)
        pct = round(comm / gross * 100, 3)
        txn, policy, cid = f"DSC{20260000000000 + i}", f"POL{i:08d}", f"CUST{100000 + i}"
        pan = f"ABCDE{1000 + i:04d}{chr(65 + i % 26)}"
        if fam == "MF":
            units, nav, folio, prem, sa = "100.0000", f"{gross / 100:.4f}", f"FOL{i:06d}", "", ""
        else:
            units, nav, folio = "", "", ""
            prem = f"{gross * 0.9:.2f}"
            sa = f"{gross * 0.9 * 20:.2f}"
        status = "REJECTED" if i % 10 == 0 else "APPROVED"
        c_str, u_str = f"{mdy(created)} {created.hour}:{created.minute:02d}", f"{mdy(updated)} {updated.hour}:{updated.minute:02d}"
        dist.append(dict(distributor_txn_id=txn, sale_date=mdy(sale), distributor_code=dcode, distributor_name=dname, customer_id=cid,
                         customer_pan=pan, product_code=code, product_name_raw=pname, product_type_raw=ptype, policy_number=policy,
                         folio_number=folio, gross_amount=f"{gross:.2f}", commission_amount=f"{comm:.2f}", region_code=rcode,
                         status=status, created_at=c_str, updated_at=u_str))
        fact.append(dict(sales_sk=str(i), distributor_txn_id=txn, sale_date_key=sale.strftime("%Y%m%d"), distributor_key=str(dkey),
                         product_key=str(pkey), customer_key=str(i), region_key=str(rkey), gross_amount=f"{gross:.2f}",
                         net_amount=f"{gross - comm:.2f}", commission_amount=f"{comm:.2f}", tax_amount="10.00", discount_amount="5.00",
                         premium_amount=prem, sum_assured=sa, units_allocated=units, nav_at_purchase=nav, commission_pct=f"{pct:.3f}",
                         txn_count="1", is_new_customer_flag="N", is_high_value_flag="Y" if gross >= 100000 else "N",
                         policy_number=policy, folio_number=folio, status=status, src_created_at=c_str, src_updated_at=u_str,
                         etl_run_id="ETL-TEST-1", etl_load_ts_utc="7/15/2026 12:00"))
        cust.append(dict(customer_key=str(i), customer_id=cid, customer_pan=pan, policy_number=policy, first_name="Asha", last_name="Rao",
                         gender="F", date_of_birth="3/30/1980", email=f"user{i}@example.com", mobile=f"98{i:08d}", address_line="1 Main Road",
                         city="Pune", state="MH", pincode="411001", country="India", kyc_status="VERIFIED", customer_segment="RETAIL",
                         annual_income="500000.00", onboarded_on="1/1/2024", active_flag="Y", created_at="1/1/2024 0:00", updated_at="2/1/2024 0:00"))
    return pd.DataFrame(dist), pd.DataFrame(fact), pd.DataFrame(cust)


def unit_settings(settings):
    """Settings copy where the master customer_id format equals the distributor format (clean synthetic world)."""
    s = copy.deepcopy(settings)
    s.rules["patterns"]["master_customer_id"] = r"^CUST\d+$"
    return s


def dm_frame_from_expected(ctx):
    """Render the independently-computed expected data mart as a DB-style all-string frame."""
    exp = ctx.expected_dm()
    out = {}
    for col in ctx.schema("dm")["columns"]:
        n = col["name"]
        if n == "dm_etl_run_id":
            out[n] = pd.Series("DM-ETL-20260715-01", index=exp.index)
        elif n == "dm_load_ts_utc":
            out[n] = pd.Series("2026-07-15 12:00:00", index=exp.index)
        elif n in exp.columns:
            s = exp[n]
            if col["type"] == "date":
                out[n] = s.dt.strftime("%Y-%m-%d").fillna("")
            elif col["type"] == "datetime":
                out[n] = s.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
            elif col["type"] == "decimal":
                out[n] = s.map(lambda x: "" if pd.isna(x) else f"{x:.{col['scale']}f}")
            elif col["type"] == "int":
                out[n] = s.map(lambda x: "" if pd.isna(x) else str(int(x)))
            else:
                out[n] = s.fillna("").astype(str)
        else:
            out[n] = pd.Series("", index=exp.index)
    return pd.DataFrame(out)
