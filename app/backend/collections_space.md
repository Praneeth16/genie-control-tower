# Genie Agent — Collections & Recovery

> Maps to the live use case **"Agentic AI for Collections & Debt Management"**.
> Paste section 4 into the Genie Agent's *Instructions* field, and load section 5 as SQL examples.
> All SQL is Spark SQL against `${FQ}`.
> **All data is synthetic.**

---

## 1. Title and description

**Title:** Collections & Recovery

**Description:** Ask plain-English questions about loan delinquency, DPD buckets, NPA, roll rates,
collections effort and recovery performance across vehicle finance, microfinance, and retail
lending. Covers which portfolios are deteriorating and why, which branches and agents are
performing, and whether recovery contact respected RBI conduct rules. Amounts are in **INR**.
The data window is **2025-03 to 2026-08**, and the current month is **2026-08**.

---

## 2. Tables in scope — 6 tables (inside the 5-7 accuracy sweet spot)

| Table | Grain | Purpose |
|---|---|---|
| `delinquency_monthly` | snapshot_month x loan_account_id | **Primary table.** DPD, bucket, NPA flag, roll direction |
| `loan_accounts` | one row per loan account | Product, branch, exposure, EMI, segment |
| `collections_activity` | one row per contact attempt | Channel, outcome, PTP, amount collected, RBI contact hour |
| `recovery_agents` | one row per agent | Agency, RBI conduct certification, complaints against |
| `repayment_schedule` | one row per amortising loan | Next due, EMIs paid/pending, mandate type |
| `branch_master` | one row per branch | City, state, region, zone |

---

## 3. Joins — declare these explicitly, Genie will not infer them

| Left | Right | Condition | Relationship |
|---|---|---|---|
| `delinquency_monthly` | `loan_accounts` | `loan_account_id = loan_account_id` | Many to one |
| `collections_activity` | `loan_accounts` | `loan_account_id = loan_account_id` | Many to one |
| `collections_activity` | `recovery_agents` | `agent_id = agent_id` | Many to one |
| `repayment_schedule` | `loan_accounts` | `loan_account_id = loan_account_id` | One to one |
| `loan_accounts` | `branch_master` | `branch_id = branch_id` | Many to one |
| `delinquency_monthly` | `branch_master` | `branch_id = branch_id` | Many to one |

`delinquency_monthly` and `collections_activity` both carry denormalised `product_code` and
`branch_id`, so product and branch filters need **no join at all**. Prefer the denormalised
columns; only join `branch_master` when the question needs city, state, region, or zone.

---

## 4. Instructions block

```
### Space metadata
You answer questions about loan collections and recovery for an Indian retail and commercial bank.
All amounts are Indian Rupees (INR). All data is synthetic. The data covers 2025-03-01 to
2026-08-01 and the current month is 2026-08-01. When a question says "now", "current", "latest"
or "this month", use snapshot_month = DATE'2026-08-01'.

### Data foundation
delinquency_monthly is the primary table for anything about delinquency, DPD, buckets, NPA or
roll rates. Its grain is one row per loan account per month, so ALWAYS aggregate; never return
raw account-level rows unless the user explicitly asks for a named account.
loan_accounts holds the current book. Use outstanding_principal for exposure, book size and
portfolio value. Never use sanctioned_amount for current exposure; that is the origination amount.
collections_activity holds one row per contact attempt, not per account.
Both delinquency_monthly and collections_activity carry product_code and branch_id already, so do
not join to loan_accounts merely to filter on product or branch.

### Business terminology
DPD means days past due. A DPD of 0 means the account is current.
Buckets are: "0-Current", "1-SMA0 (1-30)", "2-SMA1 (31-60)", "3-SMA2 (61-90)", "4-NPA (90+)".
SMA means Special Mention Account.
NPA means Non-Performing Asset, defined as dpd_days > 90, available as the is_npa flag.
GNPA percentage means gross NPA as a share of exposure:
  SUM(CASE WHEN is_npa THEN outstanding_principal ELSE 0 END) / SUM(outstanding_principal) * 100.
Delinquency rate means the share of ACCOUNTS with dpd_days > 0, unless the user says "by value",
in which case weight by outstanding_principal.
Roll-forward rate means the share of accounts whose roll_direction = 'forward' in that month.
PTP means promise to pay; those are rows where outcome = 'Contacted - PTP'.
Recovery rate means SUM(amount_collected) / SUM(overdue_amount) for the same period and scope.
Collections effort means the count of rows in collections_activity, i.e. contact attempts.
Contactability means the share of attempts whose outcome is not 'Not Reachable' and not
'Wrong Number'.
MFI means the Microfinance Group Loan product, product_code = 'MFI'.
CV means the Commercial Vehicle Loan product, product_code = 'CV'.
Vehicle Finance as a segment covers product codes CV, PV and TW.
Bucket 2 means '2-SMA1 (31-60)'.

### RBI conduct rules
RBI permits borrower contact only between 08:00 and 19:00. collections_activity.contact_hour is
the hour in 24-hour clock and within_rbi_hours is TRUE when contact fell inside that window.
Any question about conduct, breaches, or complaints against agents must use within_rbi_hours =
FALSE for out-of-hours contact, and recovery_agents.rbi_conduct_certified = FALSE for
uncertified agents. Treat a certification_expiry earlier than the activity date as uncertified.

### CRITICAL response standards
Always state the scope you applied: the month or date range, the product, and the region or
branch. Different users see different rows because row-level security is enforced, so an
unstated scope is misleading.
Round percentages to one decimal place. Format INR amounts with thousands separators, and use
crore only when the value exceeds 10,000,000 (1 crore = 10,000,000).
When a result would exceed 200 rows, aggregate further or apply a LIMIT and say so explicitly.
Never state a total that you did not compute in SQL. If the SQL returns aggregates, quote those
aggregates and nothing else.
When the user asks "why" something moved, compare the affected slice against a control slice
(other branches, other products, or the prior period) rather than describing the affected slice
alone.

### Error handling
If a question needs a column that does not exist in these six tables, say which column is missing
rather than substituting a similar one.
If a question spans customer complaints, RBI ombudsman cases, or relationship-manager incentives,
say that it belongs to a different domain agent; do not guess from the tables here.
```

---

## 5. SQL examples (load as Genie SQL examples / trusted assets)

**Q: What is the delinquency rate by product for the latest month?**
```sql
SELECT product_code,
       COUNT(*)                                              AS accounts,
       SUM(CASE WHEN dpd_days > 0 THEN 1 ELSE 0 END)         AS delinquent_accounts,
       ROUND(100.0 * SUM(CASE WHEN dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM ${FQ}.delinquency_monthly
WHERE snapshot_month = DATE'2026-08-01'
GROUP BY product_code
ORDER BY delinquency_pct DESC;
```

**Q: Show the microfinance delinquency trend in Solapur over the last 12 months.**
```sql
SELECT d.snapshot_month,
       COUNT(*)                                       AS accounts,
       ROUND(100.0 * SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) AS delinquency_pct
FROM ${FQ}.delinquency_monthly d
JOIN ${FQ}.branch_master b
  ON d.branch_id = b.branch_id
WHERE d.product_code = 'MFI'
  AND b.city = 'Solapur'
  AND d.snapshot_month >= DATE'2025-09-01'
GROUP BY d.snapshot_month
ORDER BY d.snapshot_month;
```

**Q: Which branches have the worst commercial vehicle delinquency this month, and how do they compare with the rest of the book?**
```sql
WITH cv AS (
  SELECT d.branch_id, b.city, b.region,
         COUNT(*) AS accounts,
         SUM(CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END) AS delinquent
  FROM ${FQ}.delinquency_monthly d
  JOIN ${FQ}.branch_master b
    ON d.branch_id = b.branch_id
  WHERE d.product_code = 'CV' AND d.snapshot_month = DATE'2026-08-01'
  GROUP BY d.branch_id, b.city, b.region
)
SELECT city, region, accounts, delinquent,
       ROUND(100.0 * delinquent / accounts, 1) AS delinquency_pct,
       ROUND(100.0 * SUM(delinquent) OVER () / SUM(accounts) OVER (), 1) AS book_delinquency_pct
FROM cv
ORDER BY delinquency_pct DESC
LIMIT 10;
```

**Q: What is the GNPA percentage by region for the latest month?**
```sql
SELECT b.region,
       ROUND(SUM(CASE WHEN d.is_npa THEN d.outstanding_principal ELSE 0 END), 2) AS npa_exposure_inr,
       ROUND(SUM(d.outstanding_principal), 2)                                    AS total_exposure_inr,
       ROUND(100.0 * SUM(CASE WHEN d.is_npa THEN d.outstanding_principal ELSE 0 END)
                   / SUM(d.outstanding_principal), 1)                            AS gnpa_pct
FROM ${FQ}.delinquency_monthly d
JOIN ${FQ}.branch_master b
  ON d.branch_id = b.branch_id
WHERE d.snapshot_month = DATE'2026-08-01'
GROUP BY b.region
ORDER BY gnpa_pct DESC;
```

**Q: What is the bucket-2 roll-forward rate for microfinance by month?**
```sql
SELECT snapshot_month,
       COUNT(*)                                                   AS accounts_in_bucket,
       SUM(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END) AS rolled_forward,
       ROUND(100.0 * SUM(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS roll_forward_pct
FROM ${FQ}.delinquency_monthly
WHERE product_code = 'MFI' AND dpd_bucket = '2-SMA1 (31-60)'
GROUP BY snapshot_month
ORDER BY snapshot_month;
```

**Q: How much collections effort went into Solapur microfinance versus the recovery achieved?**
```sql
SELECT DATE_TRUNC('MONTH', a.activity_date) AS activity_month,
       COUNT(*)                             AS contact_attempts,
       COUNT(DISTINCT a.loan_account_id)    AS accounts_touched,
       SUM(CASE WHEN a.outcome = 'Contacted - PTP' THEN 1 ELSE 0 END) AS ptp_count,
       ROUND(SUM(a.amount_collected), 2)    AS collected_inr
FROM ${FQ}.collections_activity a
JOIN ${FQ}.branch_master b
  ON a.branch_id = b.branch_id
WHERE a.product_code = 'MFI' AND b.city = 'Solapur'
  AND a.activity_date >= DATE'2025-09-01'
GROUP BY DATE_TRUNC('MONTH', a.activity_date)
ORDER BY activity_month;
```

**Q: Show contact attempts that breached RBI permitted hours, by branch and agency.**
```sql
SELECT b.city, r.agency_name,
       COUNT(*)                                                      AS out_of_hours_contacts,
       COUNT(DISTINCT a.agent_id)                                    AS agents_involved,
       MIN(a.contact_hour)                                           AS earliest_hour,
       MAX(a.contact_hour)                                           AS latest_hour
FROM ${FQ}.collections_activity a
JOIN ${FQ}.recovery_agents r
  ON a.agent_id = r.agent_id
JOIN ${FQ}.branch_master b
  ON a.branch_id = b.branch_id
WHERE a.within_rbi_hours = FALSE
GROUP BY b.city, r.agency_name
ORDER BY out_of_hours_contacts DESC
LIMIT 20;
```

**Q: Which recovery agents are not RBI conduct certified but still made contact this year?**
```sql
SELECT r.agent_id, r.agent_name, r.agency_name, r.rbi_conduct_certified,
       r.certification_expiry, r.complaints_against_ytd,
       COUNT(a.activity_id) AS contacts_made
FROM ${FQ}.recovery_agents r
JOIN ${FQ}.collections_activity a
  ON a.agent_id = r.agent_id
WHERE r.rbi_conduct_certified = FALSE
  AND a.activity_date >= DATE'2026-01-01'
GROUP BY r.agent_id, r.agent_name, r.agency_name, r.rbi_conduct_certified,
         r.certification_expiry, r.complaints_against_ytd
ORDER BY contacts_made DESC;
```

**Q: What is the promise-to-pay kept rate by channel?**
```sql
WITH ptp AS (
  SELECT loan_account_id, activity_date, promise_to_pay_amount, channel
  FROM ${FQ}.collections_activity
  WHERE outcome = 'Contacted - PTP' AND promise_to_pay_amount > 0
),
paid AS (
  SELECT loan_account_id, activity_date, amount_collected
  FROM ${FQ}.collections_activity
  WHERE amount_collected > 0
)
SELECT p.channel,
       COUNT(*)                                                  AS promises,
       SUM(CASE WHEN q.loan_account_id IS NOT NULL THEN 1 ELSE 0 END) AS kept,
       ROUND(100.0 * SUM(CASE WHEN q.loan_account_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS kept_pct
FROM ptp p
LEFT JOIN paid q
  ON p.loan_account_id = q.loan_account_id
 AND q.activity_date BETWEEN p.activity_date AND DATE_ADD(p.activity_date, 30)
GROUP BY p.channel
ORDER BY kept_pct DESC;
```

**Q: Which accounts are due in the next 7 days in Indore with an existing overdue position?**
```sql
SELECT s.loan_account_id, s.product_code, b.city, s.next_due_date, s.emi_amount,
       s.emis_pending, s.mandate_type, d.dpd_bucket, d.overdue_amount
FROM ${FQ}.repayment_schedule s
JOIN ${FQ}.branch_master b
  ON s.branch_id = b.branch_id
JOIN ${FQ}.delinquency_monthly d
  ON d.loan_account_id = s.loan_account_id AND d.snapshot_month = DATE'2026-08-01'
WHERE b.city = 'Indore'
  AND s.next_due_date BETWEEN DATE'2026-09-01' AND DATE'2026-09-08'
  AND d.dpd_days > 0
ORDER BY d.overdue_amount DESC
LIMIT 50;
```

---

## 6. Benchmark seeds

These are the questions whose ground-truth SQL lives in `eval/benchmarks/collections.jsonl`.
Note the two deliberately **date-pinned** questions: per the field-guide intake gate, any question
containing "latest" or "current" must either pin an as-of date or be evaluated against a freshly
computed value, never against a frozen one.

1. Delinquency rate by product, as of 2026-08-01. *(pinned)*
2. MFI delinquency percentage in Solapur, 2026-05-01. *(pinned — expect the stress peak)*
3. GNPA percentage by region, as of 2026-08-01. *(pinned)*
4. Which city has the highest CV delinquency in 2026-05? *(pinned — expect Indore)*
5. Count of out-of-hours contact attempts across the whole window.
6. Number of uncertified recovery agents who made contact in 2026.
7. Bucket-2 roll-forward percentage for MFI in 2026-05. *(pinned)*
8. Total amount collected from Solapur MFI in 2026-06.
9. Contact attempts per account touched in Solapur MFI, 2026-05 versus 2026-01.
10. Top 3 agencies by out-of-hours contacts.
