<!-- Generated 2026-10-29 13:53 UTC by tools/generate_evidence.py from the live workspace. Do not edit. -->
# 03 — Business results

_Generated 2026-10-29 13:53 UTC by `tools/generate_evidence.py` from the live workspace._

**What this proves.** The answers the Chief Risk Officer and the Head of Collections act on, computed from the governed gold tables after the final run. These are the numbers the README and the deck quote.

## Gross NPA and roll-forward, by month (last six months)

```sql
SELECT snapshot_month,
       round(100 * sum(CASE WHEN is_npa THEN outstanding_principal END) / sum(outstanding_principal), 2) AS gnpa_pct,
       round(100 * avg(CASE WHEN roll_direction = 'forward' THEN 1 ELSE 0 END), 2) AS roll_forward_pct,
       count_if(dpd_days > 0) AS delinquent_accounts
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.delinquency_monthly GROUP BY 1 ORDER BY 1 DESC LIMIT 6
```

| snapshot_month | gnpa_pct | roll_forward_pct | delinquent_accounts |
|---|---|---|---|
| 2026-08-01 | 2.95 | 9.1 | 589 |
| 2026-07-01 | 3.51 | 9.67 | 655 |
| 2026-06-01 | 3.97 | 10.48 | 735 |
| 2026-05-01 | 4.59 | 11.92 | 794 |
| 2026-04-01 | 3.89 | 10.18 | 671 |
| 2026-03-01 | 4.01 | 9.3 | 596 |

## Where the stress is: delinquency rate in the two stressed slices against the rest of the book

```sql
SELECT d.snapshot_month,
  round(100 * avg(CASE WHEN d.product_code = 'MFI' AND b.city = 'Solapur' THEN CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END END), 1) AS solapur_mfi_pct,
  round(100 * avg(CASE WHEN d.product_code = 'CV' AND b.city = 'Indore' THEN CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END END), 1) AS indore_cv_pct,
  round(100 * avg(CASE WHEN NOT (b.city IN ('Solapur', 'Indore')) THEN CASE WHEN d.dpd_days > 0 THEN 1 ELSE 0 END END), 1) AS rest_of_book_pct
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.delinquency_monthly d JOIN serverless_lakebase_praneeth_catalog.control_tower_banking.branch_master b USING (branch_id)
WHERE d.snapshot_month >= DATE'2026-02-01' GROUP BY 1 ORDER BY 1
```

| snapshot_month | solapur_mfi_pct | indore_cv_pct | rest_of_book_pct |
|---|---|---|---|
| 2026-02-01 | 11.7 | 13.1 | 8.6 |
| 2026-03-01 | 12.7 | 20.0 | 9.0 |
| 2026-04-01 | 24.3 | 24.3 | 8.7 |
| 2026-05-01 | 43.6 | 26.0 | 9.4 |
| 2026-06-01 | 34.6 | 23.8 | 9.3 |
| 2026-07-01 | 25.0 | 15.8 | 9.4 |
| 2026-08-01 | 17.8 | 16.1 | 8.4 |

## Collections effort against what was collected, Solapur microfinance, by month

```sql
SELECT date_trunc('MONTH', a.activity_date) AS month, count(*) AS contact_attempts,
       count(DISTINCT a.loan_account_id) AS accounts_contacted, round(sum(a.amount_collected)) AS collected_inr,
       round(sum(a.amount_collected) / count(*)) AS collected_per_attempt_inr
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.collections_activity a JOIN serverless_lakebase_praneeth_catalog.control_tower_banking.branch_master b USING (branch_id)
WHERE a.product_code = 'MFI' AND b.city = 'Solapur' AND a.activity_date >= DATE'2026-01-01'
GROUP BY 1 ORDER BY 1
```

| month | contact_attempts | accounts_contacted | collected_inr | collected_per_attempt_inr |
|---|---|---|---|---|
| 2026-01-01T00:00:00.000Z | 338 | 126 | 249659.0 | 739.0 |
| 2026-02-01T00:00:00.000Z | 318 | 126 | 182799.0 | 575.0 |
| 2026-03-01T00:00:00.000Z | 344 | 126 | 240572.0 | 699.0 |
| 2026-04-01T00:00:00.000Z | 644 | 126 | 480486.0 | 746.0 |
| 2026-05-01T00:00:00.000Z | 1062 | 126 | 739936.0 | 697.0 |
| 2026-06-01T00:00:00.000Z | 871 | 126 | 591727.0 | 679.0 |
| 2026-07-01T00:00:00.000Z | 542 | 126 | 365626.0 | 675.0 |
| 2026-08-01T00:00:00.000Z | 431 | 126 | 368224.0 | 854.0 |

## The collections worklist and how the bank's conduct rules say each account may be worked

```sql
SELECT recommended_treatment, count(*) AS accounts, round(sum(outstanding_principal)) AS outstanding_inr
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.collections_priority GROUP BY 1 ORDER BY accounts DESC
```

| recommended_treatment | accounts | outstanding_inr |
|---|---|---|
| Settlement or legal review | 192 | 1.38518342E8 |
| Tele-calling and digital reminder | 147 | 1.19674404E8 |
| Reassign to a certified agency and review conduct | 113 | 7.3147541E7 |
| Field visit by a certified agent | 97 | 8.105104E7 |
| Hold recovery contact until the grievance is closed | 40 | 2.8566932E7 |

## Conduct exposure: contacts outside 08:00 to 19:00 IST, and by uncertified agents (whole history)

```sql
SELECT count_if(NOT a.within_rbi_hours) AS out_of_hours_contacts,
       count_if(NOT coalesce(g.active_flag AND g.rbi_conduct_certified AND g.certification_expiry >= a.activity_date, FALSE)) AS uncertified_agent_contacts,
       count(*) AS contacts
FROM serverless_lakebase_praneeth_catalog.control_tower_banking.collections_activity a LEFT JOIN serverless_lakebase_praneeth_catalog.control_tower_banking.recovery_agents g USING (agent_id)
```

| out_of_hours_contacts | uncertified_agent_contacts | contacts |
|---|---|---|
| 2499 | 28687 | 63230 |

## Grievance: complaints open past their SLA at the reporting date, by RBI ground

```sql
SELECT rbi_category, count(*) AS open_past_sla FROM serverless_lakebase_praneeth_catalog.control_tower_banking.complaints
WHERE status = 'Open' AND sla_breached GROUP BY 1 ORDER BY 2 DESC
```

| rbi_category | open_past_sla |
|---|---|
| Recovery agents | 6 |
| Loans and advances | 1 |
