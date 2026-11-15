-- T12 New vendor billing soon after set-up: vendor created in the review year and
-- invoicing within 90 days of creation.
SELECT i.invoice_id,
       'vendor created ' || CAST(v.created_date AS DATE) || ', invoiced after ' ||
       date_diff('day', v.created_date, i.invoice_date) || ' days' AS detail
FROM invoices i JOIN vendors v USING (vendor_id)
WHERE v.created_date >= DATE '2025-01-01'
  AND date_diff('day', v.created_date, i.invoice_date) BETWEEN 0 AND 90;
