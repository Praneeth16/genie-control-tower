# Genie Agent — RM Performance & Incentives

> Maps to the live use cases **"RM Assist Agent Call Planner"** and
> **"Automated Sales Incentive Calculator"** — the customer calls this **"RM Buddy"**.
> Paste section 4 into the Genie Agent's *Instructions* field, and load section 5 as SQL examples.
> All SQL is Spark SQL against `${FQ}`.
> **All data is synthetic.**

---

## 1. Title and description

**Title:** RM Performance & Incentives

**Description:** Ask plain-English questions about relationship-manager targets, attainment,
incentive earned, product mix quality, portfolio composition and cross-sell gaps. Covers who is
performing, who is being paid, whether the payout matches portfolio quality, and where the
cross-sell opportunity sits. Amounts are in **INR**. The data window is **2025-03 to 2026-08**, and
the current month is **2026-08**.

---

## 2. Tables in scope — 6 tables

| Table | Grain | Purpose |
|---|---|---|
| `rm_achievement` | achievement_month x rm_id | **Primary table.** Actuals, attainment, incentive, quality gate |
| `rm_targets` | target_month x rm_id | Targets by product line |
| `relationship_managers` | one row per RM | Grade, branch, region, portfolio size |
| `incentive_slabs` | grade x attainment band | Payout multiple and quality gate thresholds |
| `customer_portfolio` | one row per customer | Owning RM, segment, relationship value, churn risk |
| `product_holdings` | one row per customer-product | What each customer holds, cross-sell eligibility |

---

## 3. Joins

| Left | Right | Condition | Relationship |
|---|---|---|---|
| `rm_achievement` | `rm_targets` | `achievement_month = target_month AND rm_id = rm_id` | One to one |
| `rm_achievement` | `relationship_managers` | `rm_id = rm_id` | Many to one |
| `customer_portfolio` | `relationship_managers` | `rm_id = rm_id` | Many to one |
| `product_holdings` | `customer_portfolio` | `customer_id = customer_id` | Many to one |
| `rm_achievement` | `incentive_slabs` | `rm_grade = rm_grade AND attainment_pct >= attainment_from_pct AND attainment_pct < attainment_to_pct` | Many to one, **range join** |

The slab join is a **range** join on attainment, not an equality join. Genie will not infer this —
it is spelled out in the instructions and in example 4 below.

---

## 4. Instructions block

```
### Space metadata
You answer questions about relationship-manager performance, targets, attainment and incentive
payouts for an Indian retail bank. All amounts are Indian Rupees (INR). All data is synthetic.
The data covers 2025-03-01 to 2026-08-01 and the current month is 2026-08-01. When a question says
"now", "current", "latest" or "this month", use achievement_month = DATE'2026-08-01'.
If the question names NO period at all, use the FULL data window and say so. Do not narrow to the
current month unless the question asks for it — a silently injected period can reverse the answer to
a "which is highest" question, and the user has no way to see that it happened.

### Data foundation
rm_achievement is the primary table for performance and incentive questions. Its grain is one row
per RM per month, so always aggregate unless the user names a single RM.
rm_achievement already carries branch_id, region and rm_grade, so filtering by region, branch or
grade needs NO join to relationship_managers. Join only when you need rm_name, portfolio_count,
date_joined or active_flag.
rm_targets shares the same grain. Join on BOTH achievement_month = target_month AND rm_id = rm_id.
Never join on rm_id alone, or you will fan out across 18 months and inflate every total.
incentive_slabs is joined on a RANGE: rm_grade matches AND attainment_pct is at or above
attainment_from_pct AND strictly below attainment_to_pct.
customer_portfolio is customer-level, one row per customer. product_holdings is one row per
customer-product pair, so counting rows there counts holdings, not customers.

### Business terminology
CASA means Current Account and Savings Account balances.
Attainment means attainment_pct, the average of CASA attainment and loan attainment, expressed as
a percentage where 100 means target met exactly.
Target met means attainment_pct >= 100.
Product mix score means product_mix_score, 0 to 1, measuring how evenly volume is spread across
product lines. Below 0.50 means volume is concentrated in one or two products.
Quality gate means the product-mix threshold an RM must clear to receive a full incentive payout.
quality_gate_passed is FALSE when they missed it.
Clawback means clawback_flag = TRUE: the RM reached a full-payout attainment band but failed the
quality gate, so part of the incentive is recoverable. This is the signal for incentive distortion.
Cross-sell gap means products in product_master that a customer does not hold. A customer with
products_held of 1 or 2 and cross_sell_eligible = TRUE is the prime opportunity.
Churn risk means churn_risk_score, 0 to 1. Above 0.7 warrants retention action.
League table means RMs ranked by a measure, usually attainment_pct or incentive_earned.
Incentive per rupee of business means incentive_earned divided by
(actual_casa_amount + actual_loan_amount).

### The finding to surface
Roughly 21 RMs consistently over-attain on CASA and loan volume while selling very little
insurance, which drags their product_mix_score below 0.50. They land in a full-payout attainment
band but fail the quality gate, so clawback_flag is TRUE. When a user asks about incentive
fairness, incentive quality, or who is being overpaid, find this cohort: attainment_pct >= 120 AND
product_mix_score < 0.50. Contrast their incentive_earned and actual_insurance against RMs at
similar attainment who cleared the gate.

### CRITICAL response standards
ALWAYS STATE THE COMPUTED ANSWER IN WORDS, as a number, before anything else. If you want to offer a
breakdown, state the answer first and then offer it. Never reply with only a follow-up question: the
result grid is not the answer a person reads.
When the question names a value that exists LITERALLY in a column, filter on exactly that value. Do
not widen it to related values. "Affluent customers" means customer_segment = 'Affluent', not
Affluent plus Private plus Mass Affluent.
Always state the scope: the month or range, the region or branch, and the grade. Row-level
security is enforced, so different users legitimately see different totals.
Round percentages to one decimal place. Round INR to whole rupees and use thousands separators.
Never quote a total you did not compute in SQL.
When comparing RMs, always normalise by grade or by target, because targets scale with grade and
raw volume comparisons across grades are misleading.
When a result would exceed 200 rows, aggregate further or LIMIT and say so.

### Error handling
If a question needs a column not in these six tables, name the missing column rather than
substituting a similar one.
If a question is about loan delinquency, collections, complaints or ombudsman cases, say it belongs
to a different domain agent.
```

---

## 5. SQL examples

**Q: Who are the top 10 RMs by attainment this month?**
```sql
SELECT a.rm_id, r.rm_name, a.rm_grade, a.region,
       ROUND(a.attainment_pct, 1)  AS attainment_pct,
       ROUND(a.product_mix_score, 3) AS product_mix_score,
       ROUND(a.incentive_earned, 0) AS incentive_inr,
       a.quality_gate_passed
FROM ${FQ}.rm_achievement a
JOIN ${FQ}.relationship_managers r
  ON a.rm_id = r.rm_id
WHERE a.achievement_month = DATE'2026-08-01'
ORDER BY a.attainment_pct DESC
LIMIT 10;
```

**Q: Which RMs are being paid a full incentive but failing the product-mix quality gate?**
```sql
SELECT a.rm_id, r.rm_name, a.rm_grade, a.region, a.achievement_month,
       ROUND(a.attainment_pct, 1)    AS attainment_pct,
       ROUND(a.product_mix_score, 3) AS product_mix_score,
       a.actual_insurance,
       ROUND(a.incentive_earned, 0)  AS incentive_inr,
       a.clawback_flag
FROM ${FQ}.rm_achievement a
JOIN ${FQ}.relationship_managers r
  ON a.rm_id = r.rm_id
WHERE a.clawback_flag = TRUE
  AND a.achievement_month >= DATE'2026-06-01'
ORDER BY a.incentive_earned DESC
LIMIT 50;
```

**Q: Compare incentive earned for high attainers who passed the quality gate against those who failed.**
```sql
SELECT CASE WHEN product_mix_score < 0.50 THEN 'Weak mix (<0.50)'
            ELSE 'Healthy mix (>=0.50)' END          AS mix_band,
       COUNT(*)                                       AS rm_months,
       COUNT(DISTINCT rm_id)                          AS distinct_rms,
       ROUND(AVG(attainment_pct), 1)                  AS avg_attainment_pct,
       ROUND(AVG(actual_insurance), 1)                AS avg_insurance_sold,
       ROUND(AVG(incentive_earned), 0)                AS avg_incentive_inr
FROM ${FQ}.rm_achievement
WHERE attainment_pct >= 120
GROUP BY CASE WHEN product_mix_score < 0.50 THEN 'Weak mix (<0.50)'
              ELSE 'Healthy mix (>=0.50)' END;
```

**Q: What incentive slab did each RM land in this month? (range join)**
```sql
SELECT a.rm_id, a.rm_grade,
       ROUND(a.attainment_pct, 1) AS attainment_pct,
       s.attainment_from_pct, s.attainment_to_pct,
       s.payout_pct_of_target, s.quality_gate_required, s.min_product_mix_score,
       ROUND(a.product_mix_score, 3) AS product_mix_score,
       a.quality_gate_passed,
       ROUND(a.incentive_earned, 0)  AS incentive_inr
FROM ${FQ}.rm_achievement a
JOIN ${FQ}.incentive_slabs s
  ON a.rm_grade = s.rm_grade
 AND a.attainment_pct >= s.attainment_from_pct
 AND a.attainment_pct <  s.attainment_to_pct
WHERE a.achievement_month = DATE'2026-08-01'
ORDER BY a.attainment_pct DESC
LIMIT 50;
```

**Q: Show attainment against target by region for the latest month.**
```sql
SELECT a.region,
       COUNT(*)                                     AS rms,
       ROUND(SUM(t.target_casa_amount), 0)          AS target_casa_inr,
       ROUND(SUM(a.actual_casa_amount), 0)          AS actual_casa_inr,
       ROUND(100.0 * SUM(a.actual_casa_amount) / SUM(t.target_casa_amount), 1) AS casa_attainment_pct,
       ROUND(100.0 * SUM(a.actual_loan_amount) / SUM(t.target_loan_amount), 1) AS loan_attainment_pct
FROM ${FQ}.rm_achievement a
JOIN ${FQ}.rm_targets t
  ON a.achievement_month = t.target_month AND a.rm_id = t.rm_id
WHERE a.achievement_month = DATE'2026-08-01'
GROUP BY a.region
ORDER BY casa_attainment_pct DESC;
```

**Q: Where is the biggest cross-sell gap in my portfolio?**
```sql
SELECT c.rm_id, r.rm_name, c.region,
       COUNT(*)                                                       AS customers,
       SUM(CASE WHEN c.products_held <= 2 THEN 1 ELSE 0 END)           AS thin_relationships,
       ROUND(100.0 * SUM(CASE WHEN c.products_held <= 2 THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS thin_pct,
       ROUND(SUM(c.total_relationship_value), 0)                       AS portfolio_value_inr
FROM ${FQ}.customer_portfolio c
JOIN ${FQ}.relationship_managers r
  ON c.rm_id = r.rm_id
GROUP BY c.rm_id, r.rm_name, c.region
ORDER BY thin_relationships DESC
LIMIT 20;
```

**Q: Which affluent customers hold no credit card and are cross-sell eligible?**
```sql
SELECT c.customer_id, c.rm_id, c.customer_segment, c.products_held,
       ROUND(c.total_relationship_value, 0) AS relationship_value_inr,
       ROUND(c.casa_balance, 0)             AS casa_balance_inr,
       ROUND(c.churn_risk_score, 3)         AS churn_risk
FROM ${FQ}.customer_portfolio c
WHERE c.customer_segment IN ('Affluent', 'Private', 'Mass Affluent')
  AND NOT EXISTS (
    SELECT 1 FROM ${FQ}.product_holdings h
    WHERE h.customer_id = c.customer_id AND h.product_code = 'CC' AND h.is_active
  )
ORDER BY c.total_relationship_value DESC
LIMIT 50;
```

**Q: What is the incentive cost per rupee of business by grade?**
```sql
SELECT rm_grade,
       COUNT(*)                                    AS rm_months,
       ROUND(SUM(incentive_earned), 0)             AS total_incentive_inr,
       ROUND(SUM(actual_casa_amount + actual_loan_amount), 0) AS total_business_inr,
       ROUND(1000000.0 * SUM(incentive_earned)
             / SUM(actual_casa_amount + actual_loan_amount), 2) AS incentive_per_million_inr
FROM ${FQ}.rm_achievement
WHERE achievement_month >= DATE'2026-03-01'
GROUP BY rm_grade
ORDER BY incentive_per_million_inr DESC;
```

**Q: Which RMs have high churn risk concentrated in their portfolio?**
```sql
SELECT c.rm_id, r.rm_name, c.region,
       COUNT(*)                                                        AS customers,
       SUM(CASE WHEN c.churn_risk_score > 0.7 THEN 1 ELSE 0 END)        AS high_churn_risk,
       ROUND(100.0 * SUM(CASE WHEN c.churn_risk_score > 0.7 THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS high_churn_pct,
       ROUND(SUM(CASE WHEN c.churn_risk_score > 0.7 THEN c.total_relationship_value ELSE 0 END), 0)
         AS value_at_risk_inr
FROM ${FQ}.customer_portfolio c
JOIN ${FQ}.relationship_managers r
  ON c.rm_id = r.rm_id
GROUP BY c.rm_id, r.rm_name, c.region
ORDER BY value_at_risk_inr DESC
LIMIT 20;
```

**Q: Show the monthly trend of RMs failing the quality gate.**
```sql
SELECT achievement_month,
       COUNT(*)                                                    AS rm_months,
       SUM(CASE WHEN NOT quality_gate_passed THEN 1 ELSE 0 END)     AS gate_failures,
       SUM(CASE WHEN clawback_flag THEN 1 ELSE 0 END)               AS clawbacks,
       ROUND(100.0 * SUM(CASE WHEN clawback_flag THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS clawback_pct
FROM ${FQ}.rm_achievement
GROUP BY achievement_month
ORDER BY achievement_month;
```

---

## 6. Benchmark seeds

Ground-truth SQL lives in `eval/benchmarks/rm.jsonl`. Date-pinned questions are marked.

1. Count of RM-months with clawback_flag = TRUE across the whole window.
2. Number of distinct RMs with attainment >= 120% and product_mix_score < 0.50.
3. Average incentive earned for attainment >= 120% split by mix band.
4. CASA attainment percentage by region for 2026-08. *(pinned)*
5. Top RM by attainment in 2026-08. *(pinned)*
6. Count of customers with products_held <= 2.
7. Incentive per million INR of business by grade for 2026-03 onward. *(pinned)*
8. Count of affluent-segment customers without an active credit card.
9. Which grade has the highest clawback rate.
10. Total incentive paid in 2026-08. *(pinned)*
