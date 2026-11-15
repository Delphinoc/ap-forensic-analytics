"""Load the P2P data into DuckDB, run data-quality checks, then run every red-flag test.

Run:  python -m fra.pipeline
Writes outputs/dq_results.csv, outputs/exceptions.csv, outputs/benford_*.csv
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from fra import benford

ROOT = Path(__file__).resolve().parents[1]
DATA, SQL, OUT = ROOT / "data", ROOT / "sql", ROOT / "outputs"
TABLES = ["employees", "vendors", "purchase_orders", "invoices", "payments"]

# Test metadata: name, risk weight (3 high / 2 medium / 1 low) and what it targets
TESTS = {
    "T01_duplicate_exact": ("Exact duplicate invoice", 3),
    "T02_duplicate_near": ("Near-duplicate invoice", 2),
    "T03_split_purchase": ("Split purchase below approval limit", 2),
    "T04_vendor_employee_match": ("Vendor shares employee bank account/address", 3),
    "T05_sod_self_approval": ("Requester approved own purchase", 3),
    "T06_approval_over_limit": ("Approved above delegated limit", 3),
    "T07_po_after_invoice": ("PO raised after invoice", 2),
    "T08_weekend_posting": ("Posted on a weekend", 1),
    "T09_round_amount": ("Round-sum amount", 1),
    "T10_payment_account_mismatch": ("Paid to account not on vendor master", 3),
    "T11_non_po_unapproved_vendor": ("Non-PO invoice from non-approved vendor", 2),
    "T12_new_vendor_high_activity": ("New vendor billing within 90 days", 1),
    "T13_benford_vendor": ("Vendor amounts fail Benford first-digit test", 2),
    "T14_invoiced_over_po": ("Cumulative invoices exceed PO value", 2),
}


class DataQualityError(RuntimeError):
    pass


def connect(data_dir: Path = DATA) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for t in TABLES:
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto(?, header=true)",
                    [str(data_dir / f"{t}.csv")])
    return con


def run_data_quality(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    dq = con.execute((SQL / "01_data_quality.sql").read_text()).df()
    dq["passed"] = dq.failures == 0
    return dq


def run_tests(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    frames = []
    for test_id in TESTS:
        path = SQL / "tests" / f"{test_id}.sql"
        if not path.exists():
            continue
        df = con.execute(path.read_text()).df()
        df["test_id"] = test_id
        frames.append(df)
    exc = pd.concat(frames, ignore_index=True)
    # T13 Benford (vendor-level, Python)
    inv = con.execute("SELECT invoice_id, vendor_id, amount FROM invoices").df()
    bv = benford.vendor_tests(inv)
    flagged = bv.loc[bv.flagged]
    b = inv.merge(flagged[["vendor_id", "chi2", "p_value"]], on="vendor_id")
    b = pd.DataFrame({"invoice_id": b.invoice_id,
                      "detail": "vendor " + b.vendor_id + " first digits fail Benford (chi2 "
                                + b.chi2.astype(str) + ")",
                      "test_id": "T13_benford_vendor"})
    exc = pd.concat([exc, b], ignore_index=True).drop_duplicates(["invoice_id", "test_id"])
    exc["test_name"] = exc.test_id.map(lambda t: TESTS[t][0])
    exc["weight"] = exc.test_id.map(lambda t: TESTS[t][1])
    return exc[["invoice_id", "test_id", "test_name", "weight", "detail"]]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    con = connect()
    dq = run_data_quality(con)
    dq.to_csv(OUT / "dq_results.csv", index=False)
    print(dq.to_string(index=False))
    blocking = dq[(dq.severity == "blocking") & ~dq.passed]
    if len(blocking):
        raise DataQualityError(f"blocking checks failed: {blocking.check_name.tolist()}")

    exc = run_tests(con)
    exc.to_csv(OUT / "exceptions.csv", index=False)

    inv = con.execute("SELECT invoice_id, vendor_id, amount FROM invoices").df()
    benford.digit_table(inv.amount).to_csv(OUT / "benford_population.csv", index=False)
    benford.vendor_tests(inv).to_csv(OUT / "benford_vendors.csv", index=False)
    m = benford.mad(inv.amount)
    print(f"\nPopulation Benford MAD {m:.4f} ({benford.mad_conformity(m)})")
    print("\nExceptions by test:")
    print(exc.groupby("test_id").invoice_id.nunique().to_string())


if __name__ == "__main__":
    main()
