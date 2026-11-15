# Red-flag test catalogue

Each test is a SQL query in `sql/tests/` (T13 is in Python, `fra/benford.py`). Every test returns the invoices it flags and a one-line reason. Weights are used to rank cases: 3 = high risk, 2 = medium, 1 = weak signal.

A flag means an invoice needs review. It does not mean fraud. Most tests have legitimate explanations, which are listed below.

| ID | Test | Risk it addresses | Logic | Weight | Common legitimate explanations |
|---|---|---|---|---|---|
| T01 | Exact duplicate invoice | Duplicate payment (error or fraud) | Same vendor, vendor invoice number and amount; later postings flagged | 3 | Credit note and rebill keyed with the same number |
| T02 | Near-duplicate invoice | Duplicate keyed to bypass system duplicate checks | Same vendor and amount, invoice dates ≤ 14 days apart, invoice numbers equal after removing punctuation and `A` / `-1` suffixes | 2 | Recurring orders of the same item and value |
| T03 | Split purchase | Avoiding a higher approval level | Same requester and vendor, 2+ POs within 5 days, each SGD 8,500–10,000, combined > SGD 10,000 (manager limit) | 2 | Genuinely separate orders placed close together |
| T04 | Vendor–employee match | Fictitious (ghost) vendor or conflict of interest | Vendor bank account or address equals an employee's | 3 | Employee also runs a declared, approved business |
| T05 | Self-approval | Segregation-of-duties breach | Invoice approver raised the PO | 3 | Emergency purchases with documented after-the-fact review |
| T06 | Approval above limit | Delegation-of-authority breach | Invoice amount > approver's limit | 3 | Temporary delegation not recorded in the employee master |
| T07 | PO after invoice | Retrospective PO, bypassing procurement | PO date later than invoice date | 2 | Urgent orders with a verbal approval |
| T08 | Weekend posting | Postings outside normal controls | Posting date on Saturday or Sunday | 1 | Scheduled close activity (here: the 27 Dec year-end batch) |
| T09 | Round-sum amount | Estimated or invented amounts | Amount ≥ SGD 1,000 and an exact multiple of 1,000 | 1 | Fixed-fee retainers, deposits |
| T10 | Payment account mismatch | Diverted payment, business email compromise | Paid-to account differs from the vendor master | 3 | Vendor bank change processed but master not yet updated |
| T11 | Non-PO invoice, non-approved vendor | Bypassing procurement | No PO and the vendor is not on the non-PO list (utilities) | 2 | One-off purchases allowed by policy exceptions |
| T12 | New vendor billing quickly | Ghost vendor set up and used fast | Vendor created in 2025, invoicing within 90 days of set-up | 1 | New genuine supplier onboarded for a project |
| T13 | Benford vendor test | Fabricated amounts | Chi-square first-digit test per vendor with ≥ 30 invoices, p < 0.001 | 2 | Vendors with a narrow product price range |
| T14 | Invoiced over PO | Over-billing, duplicate billing | Running invoiced total on a PO exceeds the PO amount | 2 | Approved price variations not yet amended on the PO |

## Population-level procedures

- **Data-quality checks** (`sql/01_data_quality.sql`): 7 blocking checks (unique IDs, non-null keys, positive amounts, referential integrity to vendor, employee and PO masters, one payment per invoice) and 4 warnings. The pipeline stops if a blocking check fails, so tests never run on broken data.
- **Benford population test**: first-digit mean absolute deviation (MAD) against Nigrini's thresholds. MAD is used only for the full population because it is unreliable for small samples; vendors use chi-square instead.
- **Isolation Forest** (`fra/model.py`): unsupervised anomaly score on 9 behavioural features (amount level, amount vs vendor median, share of approver limit, posting and payment timing, vendor age and volume, repeated amounts, PO presence). It never sees test results or labels.

## Case prioritisation

- **High**: any weight-3 test, or several tests whose weights total ≥ 3.
- **Medium**: one weight-2 test.
- **Low**: weak signals only (weekend, round sum, new vendor). These are monitored, not reviewed.

Within each priority, cases are ordered by rule score plus up to 2 points from the Isolation Forest percentile.
