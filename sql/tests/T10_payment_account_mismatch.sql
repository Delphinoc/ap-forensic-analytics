-- T10 Payment diverted: paid to a bank account different from the vendor master.
SELECT i.invoice_id, 'paid to ' || p.paid_to_account || ', master has ' || v.bank_account AS detail
FROM invoices i
JOIN payments p USING (invoice_id)
JOIN vendors v USING (vendor_id)
WHERE p.paid_to_account <> v.bank_account;
