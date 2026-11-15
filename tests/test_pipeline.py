import numpy as np
import pandas as pd
import pytest

from fra import benford, evaluate, generate_data, model, pipeline


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    for name, df in generate_data.build().items():
        df.to_csv(d / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    return d


@pytest.fixture(scope="session")
def con(data_dir):
    return pipeline.connect(data_dir)


@pytest.fixture(scope="session")
def exceptions(con):
    return pipeline.run_tests(con)


@pytest.fixture(scope="session")
def labels(data_dir):
    return pd.read_csv(data_dir / "injected_anomalies.csv")


# ---------- data generation ----------
def test_generation_is_reproducible():
    a = generate_data.build()["invoices"]
    b = generate_data.build()["invoices"]
    pd.testing.assert_frame_equal(a, b)


def test_answer_key_has_one_scheme_per_invoice(labels):
    assert not labels.invoice_id.duplicated().any()
    assert labels.scheme.nunique() == 11


def test_legitimate_weekend_postings_only_on_close_date(data_dir, labels):
    inv = pd.read_csv(data_dir / "invoices.csv", parse_dates=["posting_date"])
    weekend = inv[inv.posting_date.dt.dayofweek >= 5]
    legit = weekend[~weekend.invoice_id.isin(labels.invoice_id)]
    assert set(legit.posting_date.dt.date.astype(str)) == {"2025-12-27"}


# ---------- data quality ----------
def test_all_data_quality_checks_pass(con):
    dq = pipeline.run_data_quality(con)
    assert dq.passed.all(), dq[~dq.passed]


def test_blocking_check_catches_duplicate_invoice_id(data_dir, tmp_path):
    for f in data_dir.glob("*.csv"):
        (tmp_path / f.name).write_text(f.read_text())
    inv = pd.read_csv(tmp_path / "invoices.csv")
    pd.concat([inv, inv.head(1)]).to_csv(tmp_path / "invoices.csv", index=False)
    dq = pipeline.run_data_quality(pipeline.connect(tmp_path))
    row = dq.set_index("check_name").loc["invoice_id unique"]
    assert row.failures == 1 and row.severity == "blocking"


# ---------- red-flag tests ----------
@pytest.mark.parametrize("test_id", [
    "T01_duplicate_exact", "T02_duplicate_near", "T03_split_purchase",
    "T04_vendor_employee_match", "T05_sod_self_approval", "T06_approval_over_limit",
    "T07_po_after_invoice", "T10_payment_account_mismatch", "T11_non_po_unapproved_vendor",
    "T14_invoiced_over_po",
])
def test_control_tests_catch_every_target_case_with_no_false_positives(exceptions, labels, test_id):
    card = evaluate.per_test(exceptions, labels).set_index("test_id").loc[test_id]
    assert card.recall == 1.0
    assert card.precision == 1.0


def test_weak_signals_have_documented_false_positives(exceptions, labels):
    card = evaluate.per_test(exceptions, labels).set_index("test_id")
    assert card.loc["T09_round_amount", "recall"] == 1.0
    assert card.loc["T09_round_amount", "flagged_not_injected"] > 100   # fixed-fee retainers
    assert card.loc["T08_weekend_posting", "flagged_not_injected"] == 25  # year-end close batch


def test_near_duplicates_exclude_exact_duplicates(exceptions):
    t01 = set(exceptions.loc[exceptions.test_id == "T01_duplicate_exact", "invoice_id"])
    t02 = set(exceptions.loc[exceptions.test_id == "T02_duplicate_near", "invoice_id"])
    assert not t01 & t02


def test_every_injected_case_is_flagged_by_at_least_one_test(exceptions, labels):
    assert set(labels.invoice_id) <= set(exceptions.invoice_id)


# ---------- Benford ----------
def test_benford_expected_proportions():
    assert benford.EXPECTED.sum() == pytest.approx(1.0)
    assert benford.EXPECTED[0] == pytest.approx(0.30103, abs=1e-5)


def test_benford_separates_conforming_from_uniform_data():
    rng = np.random.default_rng(1)
    conforming = pd.Series(10 ** rng.uniform(1, 5, 5000))   # log-uniform follows Benford
    uniform = pd.Series(rng.uniform(4000, 9000, 5000))
    assert benford.mad_conformity(benford.mad(conforming)) in ("close conformity", "acceptable conformity")
    assert benford.chi_square(uniform)[1] < 1e-6


def test_benford_flags_only_the_colluding_vendor(data_dir):
    inv = pd.read_csv(data_dir / "invoices.csv")
    labels = pd.read_csv(data_dir / "injected_anomalies.csv")
    colluder = inv[inv.invoice_id.isin(labels.query("scheme == 'fabricated_amounts'").invoice_id)].vendor_id.unique()
    flagged = benford.vendor_tests(inv).query("flagged").vendor_id.tolist()
    assert flagged == list(colluder)


# ---------- model and case list ----------
def test_isolation_forest_beats_random_ordering(con, labels):
    feats = con.execute(model.FEATURE_SQL).df()
    feats["if_score"] = model.isolation_forest_scores(feats)
    ranked = feats.sort_values("if_score", ascending=False).invoice_id.tolist()
    base_rate = len(labels) / len(feats)
    assert evaluate.precision_at_k(ranked, labels)["precision_at_100"] > 3 * base_rate


def test_case_list_ranks_rule_evidence_above_model_only(con, exceptions):
    feats = con.execute(model.FEATURE_SQL).df()
    feats["if_score"] = model.isolation_forest_scores(feats)
    cases = model.build_case_list(feats, exceptions)
    assert len(cases) == len(feats)
    assert cases.risk_score.is_monotonic_decreasing
    assert (cases.loc[cases.priority == "High", "rule_score"] >= 3).all()
