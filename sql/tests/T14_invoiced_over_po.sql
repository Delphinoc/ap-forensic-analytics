-- T14 Over-billing: cumulative invoiced value on a PO exceeds the PO amount.
-- Flags the invoice(s) that push the running total over the PO (posting order).
WITH running AS (
    SELECT i.invoice_id, i.po_id, p.po_amount,
           SUM(i.amount) OVER (PARTITION BY i.po_id ORDER BY i.posting_date, i.invoice_id) AS cum_invoiced
    FROM invoices i JOIN purchase_orders p USING (po_id)
)
SELECT invoice_id,
       'PO ' || po_id || ' invoiced SGD ' || round(cum_invoiced, 2) || ' vs PO SGD ' || po_amount AS detail
FROM running
WHERE cum_invoiced > po_amount + 0.01;
