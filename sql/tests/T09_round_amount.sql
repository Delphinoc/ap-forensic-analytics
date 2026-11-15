-- T09 Round-sum invoice: amount is an exact multiple of SGD 1,000.
-- Weak on its own (fixed-fee retainers bill round sums); used as a scoring signal.
SELECT invoice_id, 'round amount SGD ' || CAST(amount AS BIGINT) AS detail
FROM invoices
WHERE amount >= 1000 AND amount % 1000 = 0;
