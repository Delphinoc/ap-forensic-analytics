-- T04 Vendor-employee match: vendor master bank account or address matches an employee's.
SELECT i.invoice_id,
       'vendor ' || v.vendor_id || ' shares ' ||
       CASE WHEN v.bank_account = e.bank_account THEN 'bank account' ELSE 'address' END ||
       ' with ' || e.employee_id AS detail
FROM vendors v
JOIN employees e ON v.bank_account = e.bank_account OR v.address = e.home_address
JOIN invoices i ON i.vendor_id = v.vendor_id;
