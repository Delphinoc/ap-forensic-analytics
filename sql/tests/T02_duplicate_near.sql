-- T02 Near-duplicate invoices: same vendor and amount, invoice dates within 14 days,
-- and invoice numbers that match once punctuation and trailing suffixes are removed.
-- Exact duplicates (T01) are excluded so each pair is counted once.
WITH norm AS (
    SELECT invoice_id, vendor_id, amount, invoice_date, posting_date, vendor_invoice_no,
           regexp_replace(regexp_replace(upper(vendor_invoice_no), '(-1|A)$', ''), '[^0-9A-Z]', '', 'g')
               AS inv_key
    FROM invoices
)
SELECT DISTINCT b.invoice_id,
       'matches ' || a.invoice_id || ' (' || a.vendor_invoice_no || ' vs ' || b.vendor_invoice_no || ')' AS detail
FROM norm a
JOIN norm b
  ON a.vendor_id = b.vendor_id
 AND a.amount = b.amount
 AND a.invoice_id <> b.invoice_id
 AND a.inv_key = b.inv_key
 AND a.vendor_invoice_no <> b.vendor_invoice_no
 AND ABS(date_diff('day', a.invoice_date, b.invoice_date)) <= 14
 AND (a.posting_date, a.invoice_id) < (b.posting_date, b.invoice_id);
