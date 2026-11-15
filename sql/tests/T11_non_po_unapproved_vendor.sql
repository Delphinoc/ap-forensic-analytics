-- T11 Non-PO invoice from a vendor not approved for non-PO billing (policy: utilities only).
SELECT i.invoice_id, 'no PO; vendor ' || v.vendor_id || ' not on non-PO list' AS detail
FROM invoices i JOIN vendors v USING (vendor_id)
WHERE i.po_id IS NULL AND NOT v.non_po_approved;
