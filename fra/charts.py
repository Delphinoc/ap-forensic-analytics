"""Charts for the findings memo.  Run after the model:  python -m fra.charts"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from fra import benford
from fra.pipeline import DATA, OUT, ROOT

FIG = ROOT / "reports" / "figures"
BLUE, GREY, RED = "#2b6cb0", "#a0aec0", "#c53030"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def benford_chart(inv: pd.DataFrame, vendor_id: str) -> None:
    pop = benford.digit_table(inv.amount)
    ven = benford.digit_table(inv.loc[inv.vendor_id == vendor_id, "amount"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
    for ax, t, title in ((axes[0], pop, f"All invoices (n={int(pop['count'].sum()):,})"),
                         (axes[1], ven, f"Vendor {vendor_id} (n={int(ven['count'].sum())})")):
        ax.bar(t.digit, t.observed, color=BLUE, label="Observed")
        ax.plot(t.digit, t.expected, color=RED, marker="o", label="Benford expected")
        ax.set_xticks(t.digit)
        ax.set_xlabel("First digit of invoice amount")
        ax.set_title(title)
    axes[0].set_ylabel("Share of invoices")
    axes[0].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "01_benford_first_digit.png", dpi=160)
    plt.close(fig)


def scorecard_chart(card: pd.DataFrame) -> None:
    card = card.iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(card.test_id, card.flagged, color=GREY, label="Flagged")
    ax.barh(card.test_id, card.true_positives, color=BLUE, label="Flagged and injected")
    for y, (f, p) in enumerate(zip(card.flagged, card.precision)):
        ax.text(f + 2, y, f"precision {p:.0%}", va="center", fontsize=8)
    ax.set_xlabel("Invoices flagged")
    ax.set_title("Red-flag tests: exceptions vs injected cases")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIG / "02_test_scorecard.png", dpi=160)
    plt.close(fig)


def ranking_chart(metrics: dict) -> None:
    r = metrics["ranking"]
    ks = [50, 100, 200]
    labels = {"random": "Random order", "isolation_forest_only": "Isolation Forest only",
              "rules_then_model": "Rule score + model"}
    colors = {"random": GREY, "isolation_forest_only": "#63b3ed", "rules_then_model": BLUE}
    fig, ax = plt.subplots(figsize=(7, 3.6))
    w = 0.26
    for j, key in enumerate(labels):
        vals = [r[key][f"precision_at_{k}"] for k in ks]
        ax.bar([i + (j - 1) * w for i in range(len(ks))], vals, w, color=colors[key], label=labels[key])
    ax.set_xticks(range(len(ks)), [f"Top {k}" for k in ks])
    ax.set_ylabel("Share that are injected cases")
    ax.set_ylim(0, 1)
    ax.set_title("Review-queue precision by ranking method")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "03_ranking_precision.png", dpi=160)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    inv = pd.read_csv(DATA / "invoices.csv")
    flagged_vendor = pd.read_csv(OUT / "benford_vendors.csv").query("flagged").vendor_id.iloc[0]
    benford_chart(inv, flagged_vendor)
    scorecard_chart(pd.read_csv(OUT / "test_scorecard.csv"))
    ranking_chart(json.loads((OUT / "metrics.json").read_text()))
    print("charts written to", FIG)


if __name__ == "__main__":
    main()
