"""Generate config/schema.json from the lab DDL scripts (01_/02_*.sql).

Usage:  python tools/generate_schema.py <path-to-admin-dir>
Keeps the QA schema definition traceable to the DDL (single source of truth).
"""
import json
import re
import sys
from pathlib import Path

TABLE_KEYS = {
    "dim_Distributor_sales": ("dist", "distributor_txn_id"),
    "Fact_Sales": ("fact", "sales_sk"),
    "dim_Customer_Master": ("cust", "customer_key"),
    "dm_Distributor_Sales_Customer_360": ("dm", "dm_sk"),
}
COL_RE = re.compile(
    r"^\s*`?(\w+)`?\s+(VARCHAR\(\d+\)|CHAR\(\d+\)|BIGINT|INT|DATETIME|DATE|DECIMAL\(\d+,\s*\d+\))\s*(NOT NULL|NULL)?",
    re.IGNORECASE)
SKIP = ("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "KEY")


def logical(sql_type):
    t = sql_type.upper()
    if t.startswith(("VARCHAR", "CHAR")):
        return "string", int(re.search(r"\((\d+)\)", t).group(1)), None
    if t in ("INT", "BIGINT"):
        return "int", None, None
    if t == "DATE":
        return "date", None, None
    if t == "DATETIME":
        return "datetime", None, None
    _, s = re.search(r"\((\d+),\s*(\d+)\)", t).groups()
    return "decimal", None, int(s)


def main(admin_dir):
    text = ""
    for f in sorted(Path(admin_dir).glob("0[12]_*.sql")):
        text += f.read_text(encoding="utf-8", errors="ignore") + "\n"
    schema = {}
    for m in re.finditer(r"CREATE TABLE\s+`?(\w+)`?\s*\((.*?)\)\s*ENGINE", text, re.S | re.I):
        table, body = m.group(1), m.group(2)
        if table not in TABLE_KEYS:
            continue
        key, pk = TABLE_KEYS[table]
        cols = []
        for line in body.splitlines():
            line = line.split("--")[0]
            if not line.strip() or line.strip().upper().startswith(SKIP):
                continue
            c = COL_RE.match(line)
            if not c:
                continue
            ltype, length, scale = logical(c.group(2))
            cols.append({"name": c.group(1), "sql_type": c.group(2).upper(), "type": ltype,
                         "length": length, "scale": scale,
                         "nullable": (c.group(3) or "NULL").upper() == "NULL"})
        schema[key] = {"table": table, "primary_key": pk, "columns": cols}
    out = Path(__file__).resolve().parent.parent / "config" / "schema.json"
    out.write_text(json.dumps(schema, indent=2))
    print({k: len(v["columns"]) for k, v in schema.items()}, "->", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
