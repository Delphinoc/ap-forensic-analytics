"""Generate a synthetic procure-to-pay (P2P) dataset with known, injected red flags.

All entities are fictional. Legitimate activity follows the company's policy; a set of
fraud and error schemes is then injected and every affected invoice is logged to
data/injected_anomalies.csv so the red-flag tests can be scored against a known answer.

Run:  python -m fra.generate_data
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = 42

YEAR_START = date(2025, 1, 1)
YEAR_END = date(2025, 12, 31)
YEAR_END_CLOSE = date(2025, 12, 27)  # Saturday batch posting during year-end close (legitimate)

MANAGER_LIMIT = 10_000.0
DIRECTOR_LIMIT = 50_000.0
CFO_LIMIT = 250_000.0

DEPARTMENTS = ["Operations", "IT", "Marketing", "Facilities", "HR", "Sales"]
CATEGORIES = ["IT services", "Office supplies", "Logistics", "Consulting", "Facilities",
              "Marketing", "Legal", "Equipment"]
WORDS_A = ["Apex", "Bluewave", "Cedar", "Delta", "Evergreen", "Falcon", "Granite", "Harbour",
           "Indigo", "Jade", "Kestrel", "Lumen", "Meridian", "Nimbus", "Orchid", "Pinnacle",
           "Quartz", "Riverstone", "Sterling", "Tidal", "Unity", "Vertex", "Willow", "Zenith"]
WORDS_B = ["Solutions", "Supplies", "Logistics", "Partners", "Services", "Systems", "Trading",
           "Consulting", "Works", "Technologies", "Engineering", "Media"]


def business_days(start: date, end: date) -> list[date]:
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def add_business_days(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining:
        d += timedelta(days=step)
        if d.weekday() < 5:
            remaining -= 1
    return d


def to_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


@dataclass
class Gen:
    rng: np.random.Generator

    def bank_account(self) -> str:
        r = self.rng.integers(0, 10, 10)
        return f"{''.join(map(str, r[:3]))}-{''.join(map(str, r[3:9]))}-{r[9]}"

    def address(self) -> str:
        return (f"{int(self.rng.integers(1, 400))} Example Road {int(self.rng.integers(1, 90))}, "
                f"#{int(self.rng.integers(1, 20)):02d}-{int(self.rng.integers(1, 80)):02d}, "
                f"Singapore {int(self.rng.integers(100000, 829999))}")

    def amount(self, mu: float = 7.8, sigma: float = 1.15, cap: float = 180_000) -> float:
        a = float(np.exp(self.rng.normal(mu, sigma)))
        a = min(max(a, 25.0), cap)
        a = round(a, 2)
        if a % 1000 == 0:  # legitimate non-retainer invoices are not exact round sums
            a += 0.35
        return a


def build(seed: int = SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    g = Gen(rng)
    bdays = business_days(YEAR_START, date(2025, 11, 14))  # leave room for payment in 2025

    # ---------------- employees ----------------
    emps = []
    eid = 0

    def new_emp(dept, role, limit):
        nonlocal eid
        eid += 1
        emps.append(dict(employee_id=f"E{eid:03d}", employee_name=f"Employee {eid:03d}",
                         department=dept, role=role, approval_limit=limit,
                         bank_account=g.bank_account(), home_address=g.address()))
        return f"E{eid:03d}"

    cfo = new_emp("Finance", "CFO", CFO_LIMIT)
    clerks = [new_emp("Finance", "AP Clerk", 0.0) for _ in range(5)]
    org = {}
    for dept in DEPARTMENTS:
        director = new_emp(dept, "Director", DIRECTOR_LIMIT)
        managers = [new_emp(dept, "Manager", MANAGER_LIMIT) for _ in range(2)]
        staff = [new_emp(dept, "Staff", 0.0) for _ in range(6)]
        org[dept] = dict(director=director, managers=managers, staff=staff)
    employees = pd.DataFrame(emps)

    def approver_for(dept: str, amount: float, exclude: str | None = None) -> str:
        if amount <= MANAGER_LIMIT:
            choices = [m for m in org[dept]["managers"] if m != exclude]
            return str(rng.choice(choices))
        if amount <= DIRECTOR_LIMIT:
            return org[dept]["director"]
        return cfo

    # ---------------- vendors ----------------
    vendors = []
    used_names = set()
    for i in range(1, 241):
        while True:
            name = f"{rng.choice(WORDS_A)} {rng.choice(WORDS_B)} Pte Ltd"
            if name not in used_names:
                used_names.add(name)
                break
        created = date(2018, 1, 1) + timedelta(days=int(rng.integers(0, 365 * 6.5)))
        vendors.append(dict(vendor_id=f"V{i:04d}", vendor_name=name,
                            category=str(rng.choice(CATEGORIES)), created_date=created,
                            bank_account=g.bank_account(), address=g.address(),
                            non_po_approved=False, status="Active"))
    vendors = pd.DataFrame(vendors)
    # utilities / telco billed without a PO under policy
    utility_ids = []
    for k, nm in enumerate(["Citywide Power Utilities Pte Ltd", "Metro Water Services Pte Ltd",
                            "Linkline Telecom Pte Ltd", "Northgate Gas Pte Ltd",
                            "Skyfibre Broadband Pte Ltd", "Civic Waste Management Pte Ltd"]):
        vid = f"V{241 + k:04d}"
        utility_ids.append(vid)
        vendors.loc[len(vendors)] = dict(vendor_id=vid, vendor_name=nm, category="Utilities",
                                         created_date=date(2017, 6, 1), bank_account=g.bank_account(),
                                         address=g.address(), non_po_approved=True, status="Active")
    regular_ids = vendors.loc[~vendors.non_po_approved, "vendor_id"].tolist()
    weights = 1.0 / np.arange(1, len(regular_ids) + 1) ** 0.9  # a few large vendors, a long tail
    weights /= weights.sum()
    retainer_ids = list(rng.choice(regular_ids[40:], 15, replace=False))
    vendors.loc[vendors.vendor_id.isin(retainer_ids), "category"] = "Consulting"

    pos, invs = [], []
    po_n = inv_n = 0
    inv_seq: dict[str, int] = {}

    def vendor_inv_no(vid: str) -> str:
        inv_seq[vid] = inv_seq.get(vid, int(rng.integers(1000, 9000))) + int(rng.integers(1, 4))
        return f"{vid[1:]}-{inv_seq[vid]:05d}"

    def new_po(vid, requester, dept, po_date, amount):
        nonlocal po_n
        po_n += 1
        pid = f"PO{po_n:05d}"
        pos.append(dict(po_id=pid, vendor_id=vid, requester_id=requester, department=dept,
                        po_date=po_date, po_amount=round(amount, 2)))
        return pid

    def new_inv(vid, po_id, inv_date, amount, approver, post_lag=None, inv_no=None, requester=None):
        nonlocal inv_n
        inv_n += 1
        lag = int(rng.integers(0, 8)) if post_lag is None else post_lag
        posting = add_business_days(to_business_day(inv_date), lag)
        invs.append(dict(invoice_id=f"INV{inv_n:06d}", vendor_id=vid,
                         vendor_invoice_no=inv_no or vendor_inv_no(vid), po_id=po_id,
                         invoice_date=inv_date, posting_date=posting, amount=round(amount, 2),
                         approver_id=approver, entered_by=str(rng.choice(clerks))))
        return invs[-1]

    # ---- regular PO-backed purchases ----
    for _ in range(2600):
        dept = str(rng.choice(DEPARTMENTS))
        requester = str(rng.choice(org[dept]["staff"]))
        vid = str(rng.choice(regular_ids, p=weights))
        po_date = bdays[int(rng.integers(0, len(bdays) - 40))]
        amt = g.amount()
        pid = new_po(vid, requester, dept, po_date, amt)
        parts = [amt] if rng.random() < 0.75 else [round(amt * 0.4, 2), round(amt - round(amt * 0.4, 2), 2)]
        inv_date = add_business_days(po_date, int(rng.integers(5, 30)))
        for p in parts:
            new_inv(vid, pid, inv_date, p, approver_for(dept, p))
            inv_date = add_business_days(inv_date, int(rng.integers(10, 25)))

    # ---- retainers: monthly fixed round fees against a blanket PO (legit round sums) ----
    for vid in retainer_ids:
        dept = str(rng.choice(DEPARTMENTS))
        fee = float(rng.choice([2000, 3000, 4000, 5000, 6000, 8000]))
        pid = new_po(vid, str(rng.choice(org[dept]["staff"])), dept, date(2024, 12, 16), fee * 12)
        for m in range(1, 12):
            new_inv(vid, pid, to_business_day(date(2025, m, 1)), fee, approver_for(dept, fee))

    # ---- utilities: approved non-PO invoices ----
    for vid in utility_ids:
        base = float(np.exp(rng.normal(7.3, 0.4)))
        for m in range(1, 12):
            amt = round(base * rng.uniform(0.85, 1.2), 2)
            new_inv(vid, None, to_business_day(date(2025, m, 10)), amt,
                    approver_for("Facilities", amt))

    # ---- year-end close: a Saturday batch posting (legitimate weekend postings) ----
    for _ in range(25):
        dept = str(rng.choice(DEPARTMENTS))
        vid = str(rng.choice(regular_ids, p=weights))
        po_date = date(2025, 12, 1) + timedelta(days=int(rng.integers(0, 10)))
        po_date = to_business_day(po_date)
        amt = g.amount()
        pid = new_po(vid, str(rng.choice(org[dept]["staff"])), dept, po_date, amt)
        inv = new_inv(vid, pid, date(2025, 12, 19), amt, approver_for(dept, amt))
        inv["posting_date"] = YEAR_END_CLOSE

    po_df = pd.DataFrame(pos)
    labels: list[dict] = []

    def label(invoice_id: str, scheme: str, note: str = ""):
        labels.append(dict(invoice_id=invoice_id, scheme=scheme, note=note))

    po_by_id = {p["po_id"]: p for p in pos}
    single_inv_pos = (pd.DataFrame(invs).groupby("po_id").size().loc[lambda s: s == 1].index.tolist())
    legit_pool = [i for i in invs if i["po_id"] in set(single_inv_pos)
                  and i["vendor_id"] not in retainer_ids and i["posting_date"] != YEAR_END_CLOSE]
    picked: set[str] = set()

    def pick_legit(n: int, pred=lambda inv: True) -> list[dict]:
        pool = [i for i in legit_pool if i["invoice_id"] not in picked and pred(i)]
        idx = rng.choice(len(pool), n, replace=False)
        out = [pool[k] for k in idx]
        picked.update(o["invoice_id"] for o in out)
        return out

    # A. exact duplicates: same vendor, same vendor invoice number, same amount
    for src in pick_legit(15):
        d = new_inv(src["vendor_id"], src["po_id"],
                    src["invoice_date"], src["amount"], src["approver_id"],
                    post_lag=int(rng.integers(8, 30)), inv_no=src["vendor_invoice_no"])
        label(d["invoice_id"], "duplicate_exact", f"duplicate of {src['invoice_id']}")

    # B. near duplicates: altered invoice number, same amount, dates close together
    def alter(no: str) -> str:
        k = int(rng.integers(0, 3))
        if k == 0:
            return no + "A"
        if k == 1:
            return no.replace("-", "")
        return no + "-1"

    for src in pick_legit(20):
        d = new_inv(src["vendor_id"], src["po_id"],
                    add_business_days(src["invoice_date"], int(rng.integers(1, 8))),
                    src["amount"], src["approver_id"], inv_no=alter(src["vendor_invoice_no"]))
        label(d["invoice_id"], "duplicate_near", f"re-keyed copy of {src['invoice_id']}")

    # C. split purchases: one requester raises 2-4 POs to one vendor within 3 days, each just
    #    under the manager approval limit, to avoid director approval
    for gi in range(12):
        dept = str(rng.choice(DEPARTMENTS))
        requester = str(rng.choice(org[dept]["staff"]))
        vid = str(rng.choice(regular_ids[20:]))
        d0 = bdays[int(rng.integers(0, len(bdays) - 40))]
        for k in range(int(rng.integers(2, 5))):
            amt = round(float(rng.uniform(8_600, 9_990)), 2)
            pdate = add_business_days(d0, int(rng.integers(0, 3)))
            pid = new_po(vid, requester, dept, pdate, amt)
            inv = new_inv(vid, pid, add_business_days(pdate, int(rng.integers(5, 15))), amt,
                          approver_for(dept, amt))
            label(inv["invoice_id"], "split_purchase", f"split group {gi + 1}")

    # D. ghost vendors: vendor master record carrying an employee's bank account or address,
    #    created in 2025, billing without POs
    ghost_staff = [str(rng.choice(org[d]["staff"])) for d in rng.choice(DEPARTMENTS, 3, replace=False)]
    for k, emp_id in enumerate(ghost_staff):
        emp = employees.set_index("employee_id").loc[emp_id]
        vid = f"V{247 + k:04d}"
        vendors.loc[len(vendors)] = dict(
            vendor_id=vid, vendor_name=f"{rng.choice(WORDS_A)} Advisory Services",
            category="Consulting", created_date=date(2025, int(rng.integers(2, 6)), 3),
            bank_account=emp.bank_account,
            address=emp.home_address if k == 0 else g.address(),
            non_po_approved=False, status="Active")
        created = vendors.loc[vendors.vendor_id == vid, "created_date"].iloc[0]
        for _ in range(int(rng.integers(5, 8))):
            amt = round(float(rng.uniform(2_000, 9_500)), 2)
            idate = to_business_day(created + timedelta(days=int(rng.integers(10, 180))))
            inv = new_inv(vid, None, idate, amt, approver_for(emp.department, amt))
            label(inv["invoice_id"], "ghost_vendor", f"bank account of {emp_id}")

    # E. segregation of duties: a manager raises a PO and approves the invoice themselves
    for _ in range(15):
        dept = str(rng.choice(DEPARTMENTS))
        mgr = str(rng.choice(org[dept]["managers"]))
        vid = str(rng.choice(regular_ids, p=weights))
        pdate = bdays[int(rng.integers(0, len(bdays) - 40))]
        amt = round(float(rng.uniform(800, 9_800)), 2)
        pid = new_po(vid, mgr, dept, pdate, amt)
        inv = new_inv(vid, pid, add_business_days(pdate, int(rng.integers(5, 20))), amt, mgr)
        label(inv["invoice_id"], "sod_self_approval", f"{mgr} requested and approved")

    # F. approvals above the approver's limit
    for src in pick_legit(12, lambda i: MANAGER_LIMIT < i["amount"] <= DIRECTOR_LIMIT):
        dept = po_by_id[src["po_id"]]["department"]
        src["approver_id"] = str(rng.choice(org[dept]["managers"]))
        label(src["invoice_id"], "approval_over_limit", "manager approved above SGD 10,000")

    # G. retrospective POs: PO raised after the invoice was received
    for src in pick_legit(15):
        po = po_by_id[src["po_id"]]
        po["po_date"] = add_business_days(src["invoice_date"], int(rng.integers(2, 15)))
        label(src["invoice_id"], "po_after_invoice", "PO raised after invoice date")

    # H. weekend postings outside the close calendar
    for src in pick_legit(20):
        p = src["posting_date"]
        src["posting_date"] = p + timedelta(days=(5 - p.weekday()) + int(rng.integers(0, 2)))
        label(src["invoice_id"], "weekend_posting", "posted on a weekend")

    # I. fabricated round-sum invoices against existing POs (over-billing)
    for src in pick_legit(20, lambda i: i["amount"] > 2_000):
        dept = po_by_id[src["po_id"]]["department"]
        amt = float(rng.choice([2000, 3000, 4000, 5000, 6000, 7000, 9000]))
        inv = new_inv(src["vendor_id"], src["po_id"],
                      add_business_days(src["invoice_date"], int(rng.integers(15, 40))),
                      amt, approver_for(dept, amt))
        label(inv["invoice_id"], "round_sum_billing", f"extra round-sum invoice on {src['po_id']}")

    # K. a colluding vendor whose invoice amounts are fabricated (leading digits 4-8)
    colluder = str(rng.choice([v for v in regular_ids[60:120] if v not in retainer_ids]))
    for _ in range(55):
        dept = str(rng.choice(DEPARTMENTS))
        pdate = bdays[int(rng.integers(0, len(bdays) - 40))]
        amt = round(float(rng.uniform(4_000, 8_999)), 2)
        pid = new_po(colluder, str(rng.choice(org[dept]["staff"])), dept, pdate, amt)
        inv = new_inv(colluder, pid, add_business_days(pdate, int(rng.integers(5, 25))), amt,
                      approver_for(dept, amt))
        label(inv["invoice_id"], "fabricated_amounts", f"colluding vendor {colluder}")

    invoices = pd.DataFrame(invs)
    po_df = pd.DataFrame(pos)

    # ---------------- payments ----------------
    vbank = vendors.set_index("vendor_id").bank_account.to_dict()
    pays = []
    for k, inv in enumerate(invoices.itertuples(index=False), start=1):
        pdate = add_business_days(inv.posting_date, int(rng.integers(15, 35)))
        pays.append(dict(payment_id=f"PAY{k:06d}", invoice_id=inv.invoice_id, payment_date=pdate,
                         paid_amount=inv.amount, paid_to_account=vbank[inv.vendor_id]))
    payments = pd.DataFrame(pays)
    # J. payments diverted to an account that is not on the vendor master
    lab_ids = {l["invoice_id"] for l in labels}
    clean_ids = invoices.loc[~invoices.invoice_id.isin(lab_ids)
                             & ~invoices.vendor_id.isin(retainer_ids + utility_ids)
                             & (invoices.posting_date != YEAR_END_CLOSE), "invoice_id"]
    for iid in rng.choice(clean_ids, 10, replace=False):
        payments.loc[payments.invoice_id == iid, "paid_to_account"] = g.bank_account()
        label(str(iid), "payment_account_mismatch", "paid to account not on vendor master")

    vendors["created_date"] = pd.to_datetime(vendors.created_date)
    for df, cols in ((po_df, ["po_date"]), (invoices, ["invoice_date", "posting_date"]),
                     (payments, ["payment_date"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    return dict(employees=employees, vendors=vendors, purchase_orders=po_df, invoices=invoices,
                payments=payments, injected_anomalies=pd.DataFrame(labels))


def main() -> None:
    DATA.mkdir(exist_ok=True)
    tables = build()
    for name, df in tables.items():
        df.to_csv(DATA / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        print(f"{name:22s} {len(df):>6,d} rows")


if __name__ == "__main__":
    main()
