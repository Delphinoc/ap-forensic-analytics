-- Data-quality checks run before any red-flag test.
-- 'blocking' checks stop the pipeline; 'warning' checks are reported only.
SELECT 'invoice_id unique' AS check_name, 'blocking' AS severity,
       COUNT(*) - COUNT(DISTINCT invoice_id) AS failures FROM invoices
UNION ALL
SELECT 'invoice keys not null', 'blocking',
       COUNT(*) FILTER (WHERE invoice_id IS NULL OR vendor_id IS NULL OR amount IS NULL
                        OR invoice_date IS NULL OR posting_date IS NULL OR approver_id IS NULL)
FROM invoices
UNION ALL
SELECT 'invoice amount positive', 'blocking', COUNT(*) FILTER (WHERE amount <= 0) FROM invoices
UNION ALL
SELECT 'invoice vendor exists in vendor master', 'blocking', COUNT(*)
FROM invoices i LEFT JOIN vendors v USING (vendor_id) WHERE v.vendor_id IS NULL
UNION ALL
SELECT 'invoice approver exists in employee master', 'blocking', COUNT(*)
FROM invoices i LEFT JOIN employees e ON i.approver_id = e.employee_id WHERE e.employee_id IS NULL
UNION ALL
SELECT 'invoice PO exists (when referenced)', 'blocking', COUNT(*)
FROM invoices i LEFT JOIN purchase_orders p USING (po_id)
WHERE i.po_id IS NOT NULL AND p.po_id IS NULL
UNION ALL
SELECT 'one payment per invoice', 'blocking', COUNT(*) FROM (
    SELECT i.invoice_id FROM invoices i LEFT JOIN payments p USING (invoice_id)
    GROUP BY i.invoice_id HAVING COUNT(p.payment_id) <> 1)
UNION ALL
SELECT 'paid amount equals invoice amount', 'warning', COUNT(*)
FROM invoices i JOIN payments p USING (invoice_id) WHERE ABS(i.amount - p.paid_amount) > 0.005
UNION ALL
SELECT 'posting date not before invoice date', 'warning', COUNT(*)
FROM invoices WHERE posting_date < invoice_date
UNION ALL
SELECT 'payment date not before posting date', 'warning', COUNT(*)
FROM invoices i JOIN payments p USING (invoice_id) WHERE p.payment_date < i.posting_date
UNION ALL
SELECT 'invoices dated within the review period (2025)', 'warning', COUNT(*)
FROM invoices WHERE invoice_date NOT BETWEEN DATE '2025-01-01' AND DATE '2025-12-31';
