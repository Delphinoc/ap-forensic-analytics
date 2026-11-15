"""Benford's law first-digit tests.

Population level: mean absolute deviation (MAD) against Nigrini's first-digit thresholds.
Vendor level: chi-square goodness of fit for vendors with enough invoices. MAD is not used
per vendor because it is unreliable on small samples.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

DIGITS = np.arange(1, 10)
EXPECTED = np.log10(1 + 1 / DIGITS)

# Nigrini (2012) first-digit MAD conformity ranges
MAD_THRESHOLDS = [(0.006, "close conformity"), (0.012, "acceptable conformity"),
                  (0.015, "marginally acceptable conformity")]


def first_digit(amounts: pd.Series) -> pd.Series:
    a = amounts[amounts >= 1].astype(float)
    return a.map(lambda x: int(f"{x:.6e}"[0]))


def digit_table(amounts: pd.Series) -> pd.DataFrame:
    fd = first_digit(amounts)
    counts = fd.value_counts().reindex(DIGITS, fill_value=0)
    n = int(counts.sum())
    return pd.DataFrame({"digit": DIGITS, "count": counts.values,
                         "observed": counts.values / max(n, 1), "expected": EXPECTED})


def mad(amounts: pd.Series) -> float:
    t = digit_table(amounts)
    return float(np.mean(np.abs(t.observed - t.expected)))


def mad_conformity(value: float) -> str:
    for limit, lab in MAD_THRESHOLDS:
        if value <= limit:
            return lab
    return "nonconformity"


def chi_square(amounts: pd.Series) -> tuple[float, float, int]:
    t = digit_table(amounts)
    n = int(t["count"].sum())
    stat, p = stats.chisquare(t["count"], EXPECTED * n)
    return float(stat), float(p), n


def vendor_tests(invoices: pd.DataFrame, min_invoices: int = 30, alpha: float = 0.001) -> pd.DataFrame:
    rows = []
    for vid, grp in invoices.groupby("vendor_id"):
        if len(grp) < min_invoices:
            continue
        stat, p, n = chi_square(grp.amount)
        rows.append(dict(vendor_id=vid, n_invoices=n, chi2=round(stat, 2), p_value=p,
                         flagged=p < alpha))
    return pd.DataFrame(rows).sort_values("p_value").reset_index(drop=True)
