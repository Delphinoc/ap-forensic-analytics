-- T08 Weekend posting: invoice posted on a Saturday or Sunday.
SELECT invoice_id, 'posted on ' || dayname(posting_date) || ' ' || CAST(posting_date AS DATE) AS detail
FROM invoices
WHERE dayofweek(posting_date) IN (0, 6);
