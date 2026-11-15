-- T06 Approval above authority: invoice amount exceeds the approver's delegated limit.
SELECT i.invoice_id,
       e.role || ' ' || e.employee_id || ' (limit SGD ' || CAST(e.approval_limit AS BIGINT) ||
       ') approved SGD ' || i.amount AS detail
FROM invoices i JOIN employees e ON i.approver_id = e.employee_id
WHERE i.amount > e.approval_limit;
