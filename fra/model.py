"""Unsupervised anomaly scoring (Isolation Forest) and the combined risk-ranked case list.

The model sees behavioural features only (amount patterns, timing, vendor history), not the
rule results or the injected labels, so it is an independent second view of the population.

Run after the pipeline:  python -m fra.model
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from fra import evaluate
from fra.pipeline import DATA, OUT, connect

FEATURE_SQL = """
WITH vend_med AS (
    SELECT vendor_id, median(amount) AS med_amount, COUNT(*) AS vendor_invoices
    FROM invoices GROUP BY vendor_id
)
SELECT i.invoice_id,
       ln(i.amount)                                                   AS log_amount,
       ln(i.amount / m.med_amount)                                    AS log_amount_vs_vendor_median,
       least(i.amount / e.approval_limit, 3.0)                        AS share_of_approver_limit,
       date_diff('day', i.invoice_date, i.posting_date)               AS invoice_to_posting_days,
       date_diff('day', i.posting_date, p.payment_date)               AS posting_to_payment_days,
       ln(1 + greatest(date_diff('day', v.created_date, i.invoice_date), 0)) AS log_vendor_age_days,
       ln(m.vendor_invoices)                                          AS log_vendor_invoices,
       (SELECT COUNT(*) FROM invoices j
         WHERE j.vendor_id = i.vendor_id AND j.amount = i.amount AND j.invoice_id <> i.invoice_id
           AND ABS(date_diff('day', j.invoice_date, i.invoice_date)) <= 30) AS same_amount_30d,
       CASE WHEN i.po_id IS NULL THEN 0 ELSE 1 END                     AS has_po
FROM invoices i
JOIN vend_med m USING (vendor_id)
JOIN vendors v USING (vendor_id)
JOIN employees e ON i.approver_id = e.employee_id
JOIN payments p USING (invoice_id)
ORDER BY i.invoice_id
"""
FEATURES = ["log_amount", "log_amount_vs_vendor_median", "share_of_approver_limit",
            "invoice_to_posting_days", "posting_to_payment_days", "log_vendor_age_days",
            "log_vendor_invoices", "same_amount_30d", "has_po"]


def isolation_forest_scores(feats: pd.DataFrame, seed: int = 42) -> np.ndarray:
    x = StandardScaler().fit_transform(feats[FEATURES])
    model = IsolationForest(n_estimators=400, max_samples=256, random_state=seed)
    model.fit(x)
    return -model.score_samples(x)  # higher = more anomalous


def build_case_list(feats: pd.DataFrame, exceptions: pd.DataFrame) -> pd.DataFrame:
    rule = (exceptions.drop_duplicates(["invoice_id", "test_id"])
            .groupby("invoice_id")
            .agg(rule_score=("weight", "sum"), tests_hit=("test_id", "nunique"),
                 tests=("test_id", lambda s: "; ".join(sorted(s)))))
    cases = feats[["invoice_id", "if_score"]].merge(rule, on="invoice_id", how="left")
    cases[["rule_score", "tests_hit"]] = cases[["rule_score", "tests_hit"]].fillna(0)
    cases["tests"] = cases.tests.fillna("")
    cases["if_percentile"] = cases.if_score.rank(pct=True)
    # Rules carry the evidence; the model adds up to 2 points to break ties and surface
    # unusual invoices that no rule covers.
    cases["risk_score"] = cases.rule_score + 2 * cases.if_percentile
    # Priority follows the rule evidence: any high-risk test (weight 3) or a combination of
    # tests -> High; one medium-risk test -> Medium; weak signals only -> Low (monitor).
    cases["priority"] = pd.cut(cases.rule_score, [-1, 1.5, 2.5, 99], labels=["Low", "Medium", "High"])
    return cases.sort_values(["risk_score", "if_score"], ascending=False).reset_index(drop=True)


def main() -> None:
    con = connect()
    feats = con.execute(FEATURE_SQL).df()
    feats["if_score"] = isolation_forest_scores(feats)
    exceptions = pd.read_csv(OUT / "exceptions.csv")
    labels = pd.read_csv(DATA / "injected_anomalies.csv")
    cases = build_case_list(feats, exceptions)

    inv = con.execute("SELECT invoice_id, vendor_id, vendor_invoice_no, invoice_date, amount FROM invoices").df()
    cases.merge(inv, on="invoice_id").to_csv(OUT / "case_list.csv", index=False)
    feats.to_csv(OUT / "features_and_if_scores.csv", index=False)

    n = len(feats)
    by_if = feats.sort_values("if_score", ascending=False).invoice_id.tolist()
    by_rule = cases.sort_values(["rule_score", "if_score"], ascending=False).invoice_id.tolist()
    rng = np.random.default_rng(0)
    random_rank = list(rng.permutation(feats.invoice_id))
    flagged_any = set(exceptions.invoice_id)
    flagged_strong = set(exceptions.loc[exceptions.weight >= 2, "invoice_id"])

    top200 = set(by_if[:200])
    scheme_recall_if = (labels.assign(in_top200=labels.invoice_id.isin(top200))
                        .groupby("scheme").in_top200.mean().round(3).to_dict())
    unflagged_top_if = [i for i in by_if[:100] if i not in flagged_any]

    metrics = dict(
        population=evaluate.overall(flagged_any, labels, n),
        medium_high_weight_tests_only=evaluate.overall(flagged_strong, labels, n),
        ranking=dict(random=evaluate.precision_at_k(random_rank, labels),
                     isolation_forest_only=evaluate.precision_at_k(by_if, labels),
                     rules_then_model=evaluate.precision_at_k(cases.invoice_id.tolist(), labels)),
        isolation_forest_top200_recall_by_scheme=scheme_recall_if,
        isolation_forest_top100_not_flagged_by_any_rule=len(unflagged_top_if),
        priority_counts=cases.priority.value_counts().to_dict(),
        high_priority_precision=round(cases.loc[cases.priority == "High", "invoice_id"]
                                      .isin(labels.invoice_id).mean(), 3),
    )
    per_test = evaluate.per_test(exceptions, labels)
    per_test.to_csv(OUT / "test_scorecard.csv", index=False)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    print(per_test.to_string(index=False))
    print(json.dumps(metrics, indent=2, default=str))


if __name__ == "__main__":
    main()
