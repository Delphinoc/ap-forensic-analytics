"""Score red-flag tests and the anomaly model against the injected answer key.

The answer key (data/injected_anomalies.csv) exists only because the data is synthetic.
In a real engagement there is no key: exceptions are leads for review, not findings.
"""
from __future__ import annotations

import pandas as pd

# Which injected scheme(s) each test is designed to catch
TARGETS = {
    "T01_duplicate_exact": {"duplicate_exact"},
    "T02_duplicate_near": {"duplicate_near"},
    "T03_split_purchase": {"split_purchase"},
    "T04_vendor_employee_match": {"ghost_vendor"},
    "T05_sod_self_approval": {"sod_self_approval"},
    "T06_approval_over_limit": {"approval_over_limit"},
    "T07_po_after_invoice": {"po_after_invoice"},
    "T08_weekend_posting": {"weekend_posting"},
    "T09_round_amount": {"round_sum_billing"},
    "T10_payment_account_mismatch": {"payment_account_mismatch"},
    "T11_non_po_unapproved_vendor": {"ghost_vendor"},
    "T12_new_vendor_high_activity": {"ghost_vendor"},
    "T13_benford_vendor": {"fabricated_amounts"},
    "T14_invoiced_over_po": {"round_sum_billing", "duplicate_exact", "duplicate_near"},
}


def per_test(exceptions: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    rows = []
    any_label = set(labels.invoice_id)
    for test_id, schemes in TARGETS.items():
        flagged = set(exceptions.loc[exceptions.test_id == test_id, "invoice_id"])
        target = set(labels.loc[labels.scheme.isin(schemes), "invoice_id"])
        tp = len(flagged & target)
        rows.append(dict(
            test_id=test_id, target_scheme=", ".join(sorted(schemes)), flagged=len(flagged),
            target_cases=len(target), true_positives=tp,
            precision=round(tp / len(flagged), 3) if flagged else None,
            recall=round(tp / len(target), 3) if target else None,
            flagged_other_injected=len((flagged - target) & any_label),
            flagged_not_injected=len(flagged - any_label)))
    return pd.DataFrame(rows)


def overall(flagged_ids: set[str], labels: pd.DataFrame, n_invoices: int) -> dict:
    target = set(labels.invoice_id)
    tp = len(flagged_ids & target)
    return dict(invoices=n_invoices, injected=len(target), flagged=len(flagged_ids),
                true_positives=tp, precision=round(tp / max(len(flagged_ids), 1), 3),
                recall=round(tp / len(target), 3), base_rate=round(len(target) / n_invoices, 3))


def precision_at_k(ranked_ids: list[str], labels: pd.DataFrame, ks=(50, 100, 200)) -> dict:
    target = set(labels.invoice_id)
    return {f"precision_at_{k}": round(len(set(ranked_ids[:k]) & target) / k, 3) for k in ks}
