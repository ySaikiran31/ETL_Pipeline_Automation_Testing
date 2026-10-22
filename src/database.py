"""Database module: MySQL connectivity, named-SQL execution, DB structural & SQL checks.

Checks: DB-001 .. DB-004 (connectivity/structure) and DBQ-001 .. DBQ-017 (SQL validations).
The framework is READ-ONLY: it only ever issues SELECT statements.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.config import Settings
from src.logger import get_logger
from src.normalizer import to_str
from src.registry import qa_check
from src.results import Outcome, PrerequisiteError

log = get_logger("database")


class Database:
    def __init__(self, settings: Settings):
        self.s = settings
        self.conn = None
        self.version = ""
        self._queries: Dict[str, str] = {}

    # ---------------- connection ----------------------------------------
    def connect(self) -> "Database":
        import mysql.connector
        cfg = self.s.db
        kwargs = dict(host=cfg["host"], port=cfg["port"], user=cfg["user"], database=cfg["name"],
                      connection_timeout=cfg.get("connect_timeout", 10))
        if cfg.get("password"):
            kwargs["password"] = cfg["password"]
        log.info("Connecting to MySQL %s:%s/%s as %s", cfg["host"], cfg["port"], cfg["name"], cfg["user"])
        self.conn = mysql.connector.connect(**kwargs)
        cur = self.conn.cursor()
        cur.execute("SELECT VERSION()")
        self.version = cur.fetchone()[0]
        cur.close()
        return self

    def close(self) -> None:
        try:
            if self.conn is not None and self.conn.is_connected():
                self.conn.close()
                log.info("MySQL connection closed")
        except Exception:  # noqa: BLE001
            pass

    # ---------------- query helpers --------------------------------------
    def query_df(self, sql: str, params: tuple | None = None) -> pd.DataFrame:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params or ())
            cols = [d[0] for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)
        finally:
            cur.close()

    def scalar(self, sql: str, params: tuple | None = None):
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            cur.close()

    def read_table(self, table: str) -> pd.DataFrame:
        """Whole table as normalised strings (NULL -> '')."""
        df = self.query_df(f"SELECT * FROM `{table}`")
        return pd.DataFrame({c: to_str(df[c]) for c in df.columns})

    def table_columns(self, table: str) -> pd.DataFrame:
        return self.query_df(
            "SELECT COLUMN_NAME AS column_name, DATA_TYPE AS data_type FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s ORDER BY ORDINAL_POSITION", (self.s.db["name"], table))

    def table_exists(self, table: str) -> bool:
        return self.scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                           (self.s.db["name"], table)) == 1

    def row_count(self, table: str) -> int:
        return int(self.scalar(f"SELECT COUNT(*) FROM `{table}`"))

    # ---------------- named SQL files ------------------------------------
    def named_sql(self, name: str) -> str:
        if not self._queries:
            text = (self.s.path("sql_dir") / "validation_queries.sql").read_text(encoding="utf-8")
            for m in re.finditer(r"--\s*name:\s*(\w+)\s*\n(.*?)(?=\n--\s*name:|\Z)", text, re.S):
                self._queries[m.group(1)] = m.group(2).strip().rstrip(";")
        t = {k: f"`{v}`" for k, v in self.s.tables.items()}
        return self._queries[name].format_map(t)

    def run_named(self, name: str, limit: Optional[int] = None) -> tuple[int, pd.DataFrame]:
        """Return (total offending rows, sample of up to `limit` rows)."""
        sql = self.named_sql(name)
        n = int(self.scalar(f"SELECT COUNT(*) FROM ({sql}) q"))
        limit = limit or int(self.s.execution.get("evidence_max_rows", 5000))
        sample = self.query_df(f"{sql} LIMIT {limit}") if n else pd.DataFrame()
        return n, sample


# ============================= structural checks =============================
MOD = "Database Validation"
SET = "database_validation"


@qa_check("DB-001", suite=SET, module=MOD, category="Connectivity", severity="Critical", dataset="MySQL",
          defect_area="Environment/configuration", title="Database connection can be established")
def db_connect(ctx):
    if not ctx.db_enabled:
        return Outcome.skip("Database checks disabled (--skip-db)")
    try:
        db = ctx.db
    except PrerequisiteError as exc:
        return Outcome.from_bool(False, "", str(exc), {"failure_reason": str(exc)})
    cfg = ctx.s.db
    return Outcome.from_bool(True, f"Connected to MySQL {db.version} at {cfg['host']}:{cfg['port']} db={cfg['name']} user={cfg['user']}", "")


@qa_check("DB-002", suite=SET, module=MOD, category="Availability", severity="Critical", dataset="MySQL",
          defect_area="Database", title="Required source tables and the data mart exist", requires=["db"])
def db_tables(ctx):
    rows = [{"table": t, "failure_reason": "Table does not exist"} for t in ctx.s.tables.values() if not ctx.db.table_exists(t)]
    total = len(ctx.s.tables)
    return Outcome(total=total, failed=pd.DataFrame(rows), message=f"{len(rows)} missing table(s)") if rows else \
        Outcome(total=total, message=f"All {total} tables exist: {', '.join(ctx.s.tables.values())}")


@qa_check("DB-003", suite=SET, module=MOD, category="Structure", severity="High", dataset="MySQL",
          defect_area="Database", title="Table columns and data types match the DDL-derived schema", requires=["db"])
def db_columns(ctx):
    rows, total = [], 0
    base = {"varchar": "string", "char": "string", "int": "int", "bigint": "int", "date": "date", "datetime": "datetime", "decimal": "decimal"}
    for key, tname in ctx.s.tables.items():
        actual = ctx.db.table_columns(tname).set_index("column_name")["data_type"].str.lower().to_dict()
        for col in ctx.schema(key)["columns"]:
            total += 1
            if col["name"] not in actual:
                rows.append({"table": tname, "column": col["name"], "failure_reason": "Column missing in database"})
            elif base.get(actual[col["name"]]) != col["type"]:
                rows.append({"table": tname, "column": col["name"], "expected": col["sql_type"], "actual": actual[col["name"]],
                             "failure_reason": "Data type differs from DDL"})
        rows += [{"table": tname, "column": c, "failure_reason": "Unexpected column in database"}
                 for c in actual if c not in {x["name"] for x in ctx.schema(key)["columns"]}]
    return Outcome(total=total, failed=pd.DataFrame(rows), message=f"{len(rows)} structural difference(s)") if rows else \
        Outcome(total=total, message=f"All {total} columns across {len(ctx.s.tables)} tables match schema")


@qa_check("DB-004", suite=SET, module=MOD, category="Completeness", severity="High", dataset="MySQL",
          defect_area="Database", title="All tables contain data (record counts reported)", requires=["db"])
def db_counts(ctx):
    counts = {k: ctx.db.row_count(t) for k, t in ctx.s.tables.items()}
    rows = [{"table": ctx.s.tables[k], "row_count": n, "failure_reason": "Table is empty"} for k, n in counts.items() if n == 0]
    msg = ", ".join(f"{ctx.s.tables[k]}={n:,}" for k, n in counts.items())
    return Outcome(total=len(counts), failed=pd.DataFrame(rows), message=msg) if rows else Outcome(total=len(counts), message=msg)


# ================================ SQL checks ================================
# (id, query name, title, severity, defect_area, denominator table key, category)
SQL_CHECKS = [
    ("DBQ-001", "dm_dup_txn", "SQL: no duplicate distributor_txn_id in data mart", "Critical", "Target (data mart)", "dm", "Uniqueness"),
    ("DBQ-002", "dm_dup_policy", "SQL: no duplicate policy_number in data mart", "High", "Target (data mart)", "dm", "Uniqueness"),
    ("DBQ-003", "dm_dup_sales_sk", "SQL: no duplicate sales_sk in data mart", "Critical", "Target (data mart)", "dm", "Uniqueness"),
    ("DBQ-004", "dist_dup_txn", "SQL: no duplicate distributor_txn_id in dim_Distributor_sales", "Critical", "Database", "dist", "Uniqueness"),
    ("DBQ-005", "fact_dup_txn", "SQL: no duplicate distributor_txn_id in Fact_Sales", "Critical", "Database", "fact", "Uniqueness"),
    ("DBQ-006", "cust_dup_customer_id", "SQL: no duplicate customer_id in dim_Customer_Master", "High", "Customer Master", "cust", "Uniqueness"),
    ("DBQ-007", "dm_orphan_fact", "SQL: every data-mart sales_sk exists in Fact_Sales", "Critical", "Target (data mart)", "dm", "Referential integrity"),
    ("DBQ-008", "dm_orphan_dist", "SQL: every data-mart txn+policy exists in dim_Distributor_sales", "Critical", "Target (data mart)", "dm", "Referential integrity"),
    ("DBQ-009", "dm_orphan_customer", "SQL: every data-mart customer_key exists in dim_Customer_Master", "Critical", "Target (data mart)", "dm", "Referential integrity"),
    ("DBQ-010", "dm_non_approved", "SQL: data mart holds only APPROVED transactions", "Critical", "Target (data mart)", "dm", "Business rule"),
    ("DBQ-011", "approved_missing_in_dm", "SQL: every APPROVED source transaction is present in the data mart (no missing records)", "Critical", "Target (data mart)", "fact", "Reconciliation"),
    ("DBQ-012", "dm_extra_vs_source", "SQL: no unexpected (extra) records in the data mart", "Critical", "Target (data mart)", "dm", "Reconciliation"),
    ("DBQ-013", "dm_customer_not_enriched", "SQL: data-mart rows with a customer_id are enriched from Customer Master", "Critical", "Mapping/Reference", "dm", "Referential integrity"),
    ("DBQ-014", "dm_vs_fact_measures", "SQL: data-mart measures equal Fact_Sales measures", "Critical", "Target (data mart)", "dm", "Reconciliation"),
    ("DBQ-015", "dm_vs_dist_attributes", "SQL: data-mart distributor attributes equal dim_Distributor_sales", "High", "Target (data mart)", "dm", "Reconciliation"),
    ("DBQ-016", "fact_vs_dist_core", "SQL: Fact_Sales core fields equal dim_Distributor_sales", "Critical", "Source data", "fact", "Reconciliation"),
    ("DBQ-017", "dm_future_load_ts", "SQL: data-mart load timestamp is not in the future", "Low", "Target (data mart)", "dm", "Temporal"),
]


def _make_sql_check(test_id, qname, title, severity, area, denom, category):
    @qa_check(test_id, suite=SET, module="SQL Database Validation", category=category, severity=severity,
              dataset="MySQL", defect_area=area, title=title, requires=["db"])
    def _check(ctx):
        n, sample = ctx.db.run_named(qname, int(ctx.s.execution.get("evidence_max_rows", 5000)))
        total = ctx.db.row_count(ctx.s.tables[denom])
        if n == 0:
            return Outcome(total=total, message=f"Query '{qname}' returned 0 offending rows (of {total:,} {ctx.s.tables[denom]} rows)")
        sample["failure_reason"] = title
        return Outcome(total=total, failed=sample, failed_total=n,
                       message=f"Query '{qname}' returned {n:,} offending row(s) of {total:,}")
    _check.__doc__ = f"SQL file: sql/validation_queries.sql -> {qname}"
    return _check


for _args in SQL_CHECKS:
    _make_sql_check(*_args)
