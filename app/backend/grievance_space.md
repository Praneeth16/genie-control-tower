# Genie Agent — Service & Grievance

> Maps to the live use case **"Complaints Classification DSU"**.
> Paste section 4 into the Genie Agent's *Instructions* field, and load section 5 as SQL examples.
> All SQL is Spark SQL against `${FQ}`.
> **All data is synthetic.**

---

## 1. Title and description

**Title:** Service & Grievance

**Description:** Ask plain-English questions about customer complaints, SLA performance against the
RBI Integrated Ombudsman Scheme, UPI transaction disputes, and card chargebacks. Covers complaint
volume and mix, which branches and categories breach SLA, ombudsman escalation risk, UPI auto-refund
performance, and chargeback win rates. Amounts are in **INR**. The data window is **2025-03 to
2026-08**, and the current month is **2026-08**.

---

## 2. Tables in scope — 6 tables

| Table | Grain | Purpose |
|---|---|---|
| `complaints` | one row per complaint | **Primary table.** Category, SLA state, ombudsman escalation |
| `sla_tracker` | report_month x branch x rbi_category | **Pre-aggregated.** Prefer for trends and breach rates |
| `complaint_categories` | one row per category | RBI ground of complaint, SLA days |
| `upi_disputes` | one row per dispute | Failure reason, auto-refund, resolution time |
| `chargebacks` | one row per case | Reason code, liability, outcome |
| `branch_master` | one row per branch | City, state, region, zone |

---

## 3. Joins

| Left | Right | Condition | Relationship |
|---|---|---|---|
| `complaints` | `complaint_categories` | `category_code = category_code` | Many to one |
| `complaints` | `branch_master` | `branch_id = branch_id` | Many to one |
| `sla_tracker` | `branch_master` | `branch_id = branch_id` | Many to one |
| `upi_disputes` | `branch_master` | `branch_id = branch_id` | Many to one |

`sla_tracker` already carries `region`, so regional roll-ups from it need no join.

---

## 4. Instructions block

```
### Space metadata
You answer questions about customer complaints, grievance redressal, UPI disputes and card
chargebacks for an Indian retail bank. All amounts are Indian Rupees (INR). All data is synthetic.
The data covers 2025-03-01 to 2026-08-31 and the current month is 2026-08. When a question says
"now", "current", "latest" or "this month", use August 2026.

### Data foundation
For complaint TRENDS, SLA BREACH RATES and regulatory roll-ups, PREFER sla_tracker. It is already
aggregated by month, branch and RBI category, so results stay small and cannot be silently
truncated. Only use the raw complaints table when the question needs complaint-level detail such
as severity, channel, repeat complainants, or the complaint text.
complaints is one row per complaint. An open complaint has status = 'Open' and a NULL resolved_date
and a NULL days_to_resolve.
upi_disputes is one row per dispute and is separate from complaints. A UPI dispute may or may not
also become a complaint; do not assume a one-to-one relationship between them.
chargebacks covers card disputes only, not UPI.

### Business terminology
SLA breach means the complaint took longer than its category SLA to resolve, or is still open past
that SLA. Use the sla_breached flag on complaints, or breached_sla on sla_tracker.
SLA breach rate means breached_sla / complaints_resolved from sla_tracker, or the share of
sla_breached = TRUE from complaints.
RBI CMS means the RBI Complaint Management System. A complaint with channel = 'RBI CMS' arrived
through the regulator and is a regulatory escalation in its own right.
Ombudsman escalation means escalated_to_ombudsman = TRUE. These are the most serious outcome.
Ageing means the number of days a complaint has been open: DATEDIFF(DATE'2026-08-31', received_date)
for open complaints.
Repeat complainant means repeat_complainant = TRUE, i.e. the customer has complained before.
Auto-refund rate means the share of UPI disputes with auto_refunded = TRUE. NPCI requires timed-out
or declined UPI transactions to be reversed within 30 seconds, so a falling auto-refund rate means
manual load is rising.
Chargeback win rate means Won / (Won + Lost), excluding Open and Withdrawn cases.
TAT means turnaround time, the same as days_to_resolve.
The RBI grounds of complaint are the values in rbi_category: Payment systems, Cards, Loans and
advances, Deposit accounts, Mis-selling, Recovery agents, Levy of charges, Other.
The product a complaint relates to is complaints.product_code. The codes are:
MFI = Microfinance Group Loan (say "microfinance"), CV = Commercial Vehicle Loan, PV = Passenger
Vehicle Loan, TW = Two Wheeler Loan, HL = Home Loan, PL = Personal Loan, BL = Business Loan,
CC = Credit Card. upi_disputes and chargebacks also carry product_code.
A question about complaints FROM a particular product's customers is IN SCOPE: filter on product_code
and, for a city or region, join branch_master. "Are microfinance customers in Solapur complaining
more" is answered here as complaints WHERE product_code = 'MFI' joined to branch_master WHERE
city = 'Solapur'.

### Known incident
A UPI switch degradation occurred on 2026-06-14 and 2026-06-15. On those two days UPI dispute
volume was roughly ten times normal and the auto-refund rate fell from about 78 percent to about
35 percent. The resulting customer complaints arrived two days later, on 2026-06-16 to
2026-06-18, and payment-systems SLA breaches spiked that month. When a user asks why complaints or
breaches rose in June 2026, investigate this chain rather than describing the spike alone.

### CRITICAL response standards
Always state the scope you applied: the month or date range, the category, and the branch or
region. Row-level security is enforced, so different users legitimately see different totals.
Round percentages to one decimal place. Format INR amounts with thousands separators.
Never quote a total you did not compute in SQL.
When asked "why", compare the affected slice with a control slice or the prior period.
When a result would exceed 200 rows, aggregate further or LIMIT and say so.

### Error handling
If a question needs a column not present in these six tables, name the missing column rather than
substituting a similar one.
If a question is about loan delinquency, DPD buckets, recovery-agent performance, or
relationship-manager incentives, say it belongs to a different domain agent. But do NOT decline a
question merely because it names a lending product: complaint volume, SLA breach and ombudsman
exposure FOR a product's customers is this agent's own subject. Decline only the delinquency or
recovery METRICS themselves.
```

---

## 5. SQL examples

**Q: What is the SLA breach rate by RBI category for the latest month?**
```sql
SELECT rbi_category,
       SUM(complaints_received) AS received,
       SUM(complaints_resolved) AS resolved,
       SUM(breached_sla)        AS breached,
       ROUND(100.0 * SUM(breached_sla) / NULLIF(SUM(complaints_resolved), 0), 1) AS breach_pct
FROM ${FQ}.sla_tracker
WHERE report_month = DATE'2026-08-01'
GROUP BY rbi_category
ORDER BY breach_pct DESC;
```

**Q: Show the payment-systems SLA breach rate by month over the last year.**
```sql
SELECT report_month,
       SUM(complaints_resolved) AS resolved,
       SUM(breached_sla)        AS breached,
       ROUND(100.0 * SUM(breached_sla) / NULLIF(SUM(complaints_resolved), 0), 1) AS breach_pct
FROM ${FQ}.sla_tracker
WHERE rbi_category = 'Payment systems'
  AND report_month >= DATE'2025-09-01'
GROUP BY report_month
ORDER BY report_month;
```

**Q: What happened to UPI disputes in June 2026, day by day?**
```sql
SELECT txn_date,
       COUNT(*)                                                        AS disputes,
       SUM(CASE WHEN auto_refunded THEN 1 ELSE 0 END)                  AS auto_refunded,
       ROUND(100.0 * SUM(CASE WHEN auto_refunded THEN 1 ELSE 0 END) / COUNT(*), 1) AS auto_refund_pct,
       SUM(CASE WHEN failure_reason = 'Switch degradation' THEN 1 ELSE 0 END) AS switch_degradation
FROM ${FQ}.upi_disputes
WHERE txn_date BETWEEN DATE'2026-06-01' AND DATE'2026-06-30'
GROUP BY txn_date
ORDER BY txn_date;
```

**Q: Did the June UPI incident drive a complaint spike, and how long after?**
```sql
SELECT received_date,
       COUNT(*)                                                     AS upi_complaints,
       SUM(CASE WHEN sla_breached THEN 1 ELSE 0 END)                AS breached,
       ROUND(AVG(days_to_resolve), 1)                               AS avg_tat_days
FROM ${FQ}.complaints
WHERE category_code = 'UPI'
  AND received_date BETWEEN DATE'2026-06-10' AND DATE'2026-06-25'
GROUP BY received_date
ORDER BY received_date;
```

**Q: Which branches have the most open complaints past SLA right now?**
```sql
SELECT b.city, b.region, c.branch_id,
       COUNT(*)                                                   AS open_complaints,
       SUM(CASE WHEN c.sla_breached THEN 1 ELSE 0 END)            AS past_sla,
       ROUND(AVG(DATEDIFF(DATE'2026-08-31', c.received_date)), 1) AS avg_age_days
FROM ${FQ}.complaints c
JOIN ${FQ}.branch_master b
  ON c.branch_id = b.branch_id
WHERE c.status = 'Open'
GROUP BY b.city, b.region, c.branch_id
ORDER BY past_sla DESC
LIMIT 15;
```

**Q: How many complaints were escalated to the RBI Ombudsman, by category?**
```sql
SELECT cc.rbi_category, cc.category_name,
       COUNT(*)                                                        AS complaints,
       SUM(CASE WHEN c.escalated_to_ombudsman THEN 1 ELSE 0 END)       AS escalations,
       ROUND(100.0 * SUM(CASE WHEN c.escalated_to_ombudsman THEN 1 ELSE 0 END) / COUNT(*), 2)
         AS escalation_pct
FROM ${FQ}.complaints c
JOIN ${FQ}.complaint_categories cc
  ON c.category_code = cc.category_code
GROUP BY cc.rbi_category, cc.category_name
ORDER BY escalations DESC;
```

**Q: What is the complaint mix by channel and severity this month?**
```sql
SELECT channel, severity, COUNT(*) AS complaints
FROM ${FQ}.complaints
WHERE received_date >= DATE'2026-08-01'
GROUP BY channel, severity
ORDER BY channel, complaints DESC;
```

**Q: What is the chargeback win rate by merchant category?**
```sql
SELECT merchant_category,
       COUNT(*)                                              AS cases,
       SUM(CASE WHEN status = 'Won'  THEN 1 ELSE 0 END)       AS won,
       SUM(CASE WHEN status = 'Lost' THEN 1 ELSE 0 END)       AS lost,
       ROUND(100.0 * SUM(CASE WHEN status = 'Won' THEN 1 ELSE 0 END)
                   / NULLIF(SUM(CASE WHEN status IN ('Won','Lost') THEN 1 ELSE 0 END), 0), 1)
         AS win_rate_pct,
       ROUND(SUM(recovered_amount), 2)                        AS recovered_inr
FROM ${FQ}.chargebacks
GROUP BY merchant_category
ORDER BY cases DESC;
```

**Q: Which recovery-agent conduct complaints escalated to the ombudsman?**
```sql
SELECT c.complaint_id, c.received_date, b.city, c.severity, c.status,
       c.days_to_resolve, c.sla_days, c.sla_breached, c.complaint_text
FROM ${FQ}.complaints c
JOIN ${FQ}.branch_master b
  ON c.branch_id = b.branch_id
WHERE c.category_code = 'REC'
  AND c.escalated_to_ombudsman = TRUE
ORDER BY c.received_date DESC
LIMIT 50;
```

**Q: How many repeat complainants do we have and what do they complain about?**
```sql
SELECT cc.category_name,
       COUNT(*)                                                  AS complaints,
       SUM(CASE WHEN c.repeat_complainant THEN 1 ELSE 0 END)      AS from_repeat_complainants,
       ROUND(100.0 * SUM(CASE WHEN c.repeat_complainant THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS repeat_pct
FROM ${FQ}.complaints c
JOIN ${FQ}.complaint_categories cc
  ON c.category_code = cc.category_code
GROUP BY cc.category_name
ORDER BY repeat_pct DESC;
```

---

## 6. Benchmark seeds

Ground-truth SQL lives in `eval/benchmarks/grievance.jsonl`. Date-pinned questions are marked.

1. SLA breach rate by RBI category for 2026-08. *(pinned)*
2. Payment-systems SLA breach percentage in 2026-06. *(pinned — expect the June spike)*
3. UPI dispute count on 2026-06-14. *(pinned — expect roughly ten times baseline)*
4. Auto-refund percentage on 2026-06-15 versus 2026-06-10. *(pinned)*
5. UPI complaint count on 2026-06-17. *(pinned — expect the lagged spike)*
6. Total ombudsman escalations in the full window.
7. Chargeback win rate overall.
8. Count of open complaints past SLA as of 2026-08-31. *(pinned)*
9. Which RBI category has the highest ombudsman escalation percentage.
10. Number of complaints that arrived through the RBI CMS channel.
