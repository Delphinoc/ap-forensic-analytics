-- T03 Split purchases: the same requester raises 2+ POs to the same vendor within 3 days,
-- each between 85% and 100% of the SGD 10,000 manager approval limit, together exceeding it.
WITH near_limit AS (
    SELECT po_id, requester_id, vendor_id, po_date, po_amount
    FROM purchase_orders
    WHERE po_amount >= 8500 AND po_amount <= 10000
),
grp AS (
    SELECT a.po_id,
           COUNT(*) AS n_pos,
           SUM(b.po_amount) AS combined
    FROM near_limit a
    JOIN near_limit b
      ON a.requester_id = b.requester_id
     AND a.vendor_id = b.vendor_id
     AND ABS(date_diff('day', a.po_date, b.po_date)) <= 5
    GROUP BY a.po_id
    HAVING COUNT(*) >= 2 AND SUM(b.po_amount) > 10000
)
SELECT i.invoice_id,
       g.n_pos || ' near-limit POs within 5 days, combined SGD ' || round(g.combined, 2) AS detail
FROM grp g JOIN invoices i USING (po_id);
