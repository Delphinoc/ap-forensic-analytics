-- T07 Retrospective PO: the PO is dated after the vendor's invoice.
SELECT i.invoice_id,
       'PO ' || p.po_id || ' raised ' || date_diff('day', i.invoice_date, p.po_date) ||
       ' days after invoice' AS detail
FROM invoices i JOIN purchase_orders p USING (po_id)
WHERE p.po_date > i.invoice_date;
