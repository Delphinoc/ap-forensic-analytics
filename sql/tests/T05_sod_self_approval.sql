-- T05 Segregation of duties: invoice approved by the person who raised the PO.
SELECT i.invoice_id, 'approver ' || i.approver_id || ' also raised ' || p.po_id AS detail
FROM invoices i JOIN purchase_orders p USING (po_id)
WHERE i.approver_id = p.requester_id;
