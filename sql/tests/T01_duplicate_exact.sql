-- T01 Exact duplicate invoices: same vendor, same vendor invoice number, same amount.
-- The earliest-posted copy is treated as the original; later copies are flagged.
SELECT invoice_id,
       'same vendor invoice no. and amount as ' || first_id AS detail
FROM (
    SELECT invoice_id,
           FIRST_VALUE(invoice_id) OVER w AS first_id,
           ROW_NUMBER() OVER w AS rn
    FROM invoices
    WINDOW w AS (PARTITION BY vendor_id, vendor_invoice_no, amount
                 ORDER BY posting_date, invoice_id)
)
WHERE rn > 1;
