-- CORE: the bank's conformed book, private to the pipeline.
--
-- PRIVATE on purpose. These are the tables the pipeline computes FROM; the governed gold tables in
-- 04_gold.sql are the ones people and agents query. Row filters and column masks live only on gold, so
-- nothing the pipeline derives (the priority score, the SLA rollup, the row-count manifest) can ever be
-- computed through somebody's row filter. Policies change who sees an answer, never the answer.
--
-- This is also where the business rules live that used to be computed in Python before the data was
-- written: DPD bucket, NPA, roll direction, the RBI contact-hours flag, SLA breach, RM attainment,
-- incentive, quality gate and clawback. They are now SQL a risk or audit team can read.
--
-- Pipeline configuration: ${as_of_date} = the date the book is reported as at (2026-08-31).

-- ============================================================ reference data and masters
-- Snapshots can be re-sent; the latest landed copy of each key wins.

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_branch_master AS
SELECT upper(trim(branch_id)) AS branch_id, trim(branch_name) AS branch_name, trim(city) AS city,
       trim(state) AS state, trim(region) AS region, trim(zone) AS zone,
       try_cast(opened_date AS DATE) AS opened_date, try_cast(employee_count AS INT) AS employee_count
FROM bronze_branch_master
QUALIFY row_number() OVER (PARTITION BY upper(trim(branch_id)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_product_master AS
SELECT upper(trim(product_code)) AS product_code, trim(product_name) AS product_name,
       trim(segment) AS segment, try_cast(is_secured AS BOOLEAN) AS is_secured
FROM bronze_product_master
QUALIFY row_number() OVER (PARTITION BY upper(trim(product_code)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_complaint_categories AS
SELECT upper(trim(category_code)) AS category_code, trim(category_name) AS category_name,
       trim(rbi_category) AS rbi_category, try_cast(sla_days AS INT) AS sla_days
FROM bronze_complaint_categories
QUALIFY row_number() OVER (PARTITION BY upper(trim(category_code)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_incentive_slabs AS
SELECT trim(slab_id) AS slab_id, trim(rm_grade) AS rm_grade,
       try_cast(attainment_from_pct AS DOUBLE) AS attainment_from_pct,
       try_cast(attainment_to_pct AS DOUBLE) AS attainment_to_pct,
       try_cast(payout_pct_of_target AS DOUBLE) AS payout_pct_of_target,
       try_cast(quality_gate_required AS BOOLEAN) AS quality_gate_required,
       try_cast(min_product_mix_score AS DOUBLE) AS min_product_mix_score
FROM bronze_incentive_slabs
QUALIFY row_number() OVER (PARTITION BY trim(slab_id) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_recovery_agents AS
SELECT upper(trim(agent_id)) AS agent_id, trim(agent_name) AS agent_name, trim(agency_name) AS agency_name,
       upper(trim(branch_id)) AS branch_id, trim(region) AS region,
       try_cast(rbi_conduct_certified AS BOOLEAN) AS rbi_conduct_certified,
       try_cast(certification_expiry AS DATE) AS certification_expiry,
       try_cast(active_flag AS BOOLEAN) AS active_flag,
       try_cast(complaints_against_ytd AS INT) AS complaints_against_ytd
FROM bronze_recovery_agents
QUALIFY row_number() OVER (PARTITION BY upper(trim(agent_id)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_relationship_managers AS
SELECT upper(trim(rm_id)) AS rm_id, trim(rm_name) AS rm_name, upper(trim(branch_id)) AS branch_id,
       trim(region) AS region, trim(zone) AS zone, trim(rm_grade) AS rm_grade,
       try_cast(date_joined AS DATE) AS date_joined, try_cast(portfolio_count AS INT) AS portfolio_count,
       try_cast(active_flag AS BOOLEAN) AS active_flag
FROM bronze_relationship_managers
QUALIFY row_number() OVER (PARTITION BY upper(trim(rm_id)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_customer_portfolio AS
SELECT upper(trim(customer_id)) AS customer_id, upper(trim(rm_id)) AS rm_id, upper(trim(branch_id)) AS branch_id,
       trim(region) AS region, trim(customer_segment) AS customer_segment,
       try_cast(relationship_start AS DATE) AS relationship_start,
       try_cast(total_relationship_value AS DOUBLE) AS total_relationship_value,
       try_cast(products_held AS INT) AS products_held, try_cast(casa_balance AS DOUBLE) AS casa_balance,
       trim(risk_rating) AS risk_rating, try_cast(nri_flag AS BOOLEAN) AS nri_flag,
       try_cast(churn_risk_score AS DOUBLE) AS churn_risk_score
FROM bronze_customer_portfolio
QUALIFY row_number() OVER (PARTITION BY upper(trim(customer_id)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_product_holdings AS
SELECT trim(holding_id) AS holding_id, upper(trim(customer_id)) AS customer_id, upper(trim(rm_id)) AS rm_id,
       upper(trim(product_code)) AS product_code, try_cast(opened_date AS DATE) AS opened_date,
       try_cast(balance_or_limit AS DOUBLE) AS balance_or_limit, try_cast(is_active AS BOOLEAN) AS is_active,
       try_cast(cross_sell_eligible AS BOOLEAN) AS cross_sell_eligible
FROM bronze_product_holdings
QUALIFY row_number() OVER (PARTITION BY trim(holding_id) ORDER BY _ingested_at DESC) = 1;

-- Loans: product codes arrive lower-case with trailing spaces from one LOS screen, so they are
-- normalised before the join. A code the bank does not sell is not silently dropped by the inner join:
-- it goes to quarantine_orphans below.
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_loans_typed AS
SELECT upper(trim(loan_account_id)) AS loan_account_id, upper(trim(customer_id)) AS customer_id,
       upper(trim(product_code)) AS product_code, upper(trim(branch_id)) AS branch_id,
       try_cast(disbursed_date AS DATE) AS disbursed_date,
       try_cast(sanctioned_amount AS DOUBLE) AS sanctioned_amount,
       try_cast(outstanding_principal AS DOUBLE) AS outstanding_principal,
       try_cast(interest_rate AS DOUBLE) AS interest_rate, try_cast(tenure_months AS INT) AS tenure_months,
       try_cast(emi_amount AS DOUBLE) AS emi_amount, trim(customer_segment) AS customer_segment,
       try_cast(is_restructured AS BOOLEAN) AS is_restructured, _source_path
FROM bronze_loan_accounts
QUALIFY row_number() OVER (PARTITION BY upper(trim(loan_account_id)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_loan_accounts AS
SELECT l.* EXCEPT (_source_path), b.region
FROM core_loans_typed l
JOIN core_product_master p ON p.product_code = l.product_code
JOIN core_branch_master b ON b.branch_id = l.branch_id;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_repayment_schedule AS
SELECT upper(trim(r.loan_account_id)) AS loan_account_id, l.product_code, l.branch_id, l.region,
       try_cast(r.next_due_date AS DATE) AS next_due_date, try_cast(r.emi_amount AS DOUBLE) AS emi_amount,
       try_cast(r.emis_paid AS INT) AS emis_paid, try_cast(r.emis_pending AS INT) AS emis_pending,
       try_cast(r.last_payment_date AS DATE) AS last_payment_date,
       try_cast(r.last_payment_amount AS DOUBLE) AS last_payment_amount, trim(r.mandate_type) AS mandate_type
FROM bronze_repayment_schedule r
JOIN core_loan_accounts l ON l.loan_account_id = upper(trim(r.loan_account_id))
QUALIFY row_number() OVER (PARTITION BY upper(trim(r.loan_account_id)) ORDER BY r._ingested_at DESC) = 1;

-- ============================================================ delinquency, with the regulatory rules
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_delinquency AS
WITH latest AS (
  SELECT * FROM silver_delinquency
  QUALIFY row_number() OVER (PARTITION BY snapshot_month, loan_account_id ORDER BY _ingested_at DESC) = 1
),
bucketed AS (
  SELECT d.snapshot_month, d.loan_account_id, l.product_code, l.branch_id, l.region, d.dpd_days,
         -- RBI Special Mention Account ageing. NPA is more than 90 days past due.
         CASE WHEN d.dpd_days = 0 THEN '0-Current'
              WHEN d.dpd_days <= 30 THEN '1-SMA0 (1-30)'
              WHEN d.dpd_days <= 60 THEN '2-SMA1 (31-60)'
              WHEN d.dpd_days <= 90 THEN '3-SMA2 (61-90)'
              ELSE '4-NPA (90+)' END AS dpd_bucket,
         d.outstanding_principal, d.overdue_amount, d.dpd_days > 90 AS is_npa
  FROM latest d
  JOIN core_loan_accounts l ON l.loan_account_id = d.loan_account_id
)
SELECT *,
       -- Against the account's ACTUAL previous snapshot. The generator used to re-derive a "previous" DPD
       -- with fresh random draws, so the stored roll direction disagreed with the stored history; a lag
       -- over the snapshots is the only definition an auditor can reproduce.
       CASE WHEN lag(dpd_bucket) OVER w IS NULL OR lag(dpd_bucket) OVER w = dpd_bucket THEN 'stable'
            WHEN dpd_bucket > lag(dpd_bucket) OVER w THEN 'forward'
            ELSE 'backward' END AS roll_direction
FROM bucketed
WINDOW w AS (PARTITION BY loan_account_id ORDER BY snapshot_month);

-- ============================================================ contact attempts, with the RBI hours rule
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_collections_activity AS
WITH deduped AS (
  SELECT * FROM silver_collections_activity
  QUALIFY row_number() OVER (PARTITION BY activity_id ORDER BY _ingested_at, _source_path) = 1
)
SELECT a.activity_id, CAST(a.contact_ts_ist AS DATE) AS activity_date, a.contact_ts_ist,
       ${catalog}.${schema}.ist_hour(a.contact_epoch) AS contact_hour,
       a.loan_account_id, l.product_code, l.branch_id, l.region, a.agent_id, a.channel, a.outcome,
       coalesce(a.promise_to_pay_amount, 0) AS promise_to_pay_amount,
       coalesce(a.amount_collected, 0) AS amount_collected,
       ${catalog}.${schema}.is_within_rbi_conduct_hours(a.contact_epoch) AS within_rbi_hours,
       a.source_system
FROM deduped a
JOIN core_loan_accounts l ON l.loan_account_id = a.loan_account_id;

-- ============================================================ complaints, with SLA rules
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_complaints AS
WITH deduped AS (
  SELECT * FROM silver_complaints
  QUALIFY row_number() OVER (PARTITION BY complaint_id ORDER BY _ingested_at, _source_path) = 1
)
SELECT c.complaint_id, c.received_date, c.channel, c.category_code, k.rbi_category, c.customer_id,
       c.branch_id, b.region, c.product_code, c.severity, c.status, c.resolved_date,
       datediff(c.resolved_date, c.received_date) AS days_to_resolve,
       k.sla_days,
       -- A closed complaint breached if it took longer than its SLA; an open one breached once it has been
       -- open longer than its SLA as at the reporting date. One as-of date for the whole book, or the same
       -- question gets two defensible answers.
       CASE WHEN c.status = 'Open' THEN datediff(DATE '${as_of_date}', c.received_date) > k.sla_days
            ELSE datediff(c.resolved_date, c.received_date) > k.sla_days END AS sla_breached,
       c.escalated_to_ombudsman, c.repeat_complainant, c.complaint_text
FROM deduped c
JOIN core_complaint_categories k ON k.category_code = c.category_code
JOIN core_branch_master b ON b.branch_id = c.branch_id;

-- ============================================================ disputes and chargebacks
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_upi_disputes AS
SELECT u.* EXCEPT (dq_reason, _source_path, _ingested_at), b.region
FROM silver_upi_disputes u
JOIN core_branch_master b ON b.branch_id = u.branch_id
QUALIFY row_number() OVER (PARTITION BY u.dispute_id ORDER BY u._ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_chargebacks AS
SELECT * EXCEPT (dq_reason, _source_path, _ingested_at)
FROM silver_chargebacks
QUALIFY row_number() OVER (PARTITION BY chargeback_id ORDER BY _ingested_at DESC) = 1;

-- ============================================================ RM targets and the incentive rules
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_rm_targets AS
SELECT try_cast(target_month AS DATE) AS target_month, upper(trim(rm_id)) AS rm_id,
       upper(trim(branch_id)) AS branch_id, trim(region) AS region, trim(rm_grade) AS rm_grade,
       try_cast(target_casa_amount AS DOUBLE) AS target_casa_amount,
       try_cast(target_loan_amount AS DOUBLE) AS target_loan_amount,
       try_cast(target_cards AS INT) AS target_cards, try_cast(target_insurance AS INT) AS target_insurance,
       try_cast(target_product_mix_score AS DOUBLE) AS target_product_mix_score
FROM bronze_rm_targets
QUALIFY row_number() OVER (PARTITION BY target_month, upper(trim(rm_id)) ORDER BY _ingested_at DESC) = 1;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW core_rm_achievement AS
WITH a AS (
  SELECT try_cast(achievement_month AS DATE) AS achievement_month, upper(trim(rm_id)) AS rm_id,
         upper(trim(branch_id)) AS branch_id, trim(region) AS region, trim(rm_grade) AS rm_grade,
         try_cast(actual_casa_amount AS DOUBLE) AS actual_casa_amount,
         try_cast(actual_loan_amount AS DOUBLE) AS actual_loan_amount,
         try_cast(actual_cards AS INT) AS actual_cards, try_cast(actual_insurance AS INT) AS actual_insurance,
         try_cast(product_mix_score AS DOUBLE) AS product_mix_score
  FROM bronze_rm_achievement
  QUALIFY row_number() OVER (PARTITION BY achievement_month, upper(trim(rm_id)) ORDER BY _ingested_at DESC) = 1
),
attained AS (
  SELECT a.*, t.target_casa_amount, t.target_loan_amount,
         -- Attainment is the average of CASA and loan attainment.
         round((a.actual_casa_amount / t.target_casa_amount + a.actual_loan_amount / t.target_loan_amount) / 2 * 100, 2)
           AS attainment_pct
  FROM a JOIN core_rm_targets t ON t.target_month = a.achievement_month AND t.rm_id = a.rm_id
),
slabbed AS (
  SELECT x.*, coalesce(s.payout_pct_of_target, 0) AS payout,
         coalesce(s.quality_gate_required, FALSE) AS gate_required,
         coalesce(s.min_product_mix_score, 0) AS gate_min
  FROM attained x
  LEFT JOIN core_incentive_slabs s
    ON s.rm_grade = x.rm_grade AND x.attainment_pct >= s.attainment_from_pct AND x.attainment_pct < s.attainment_to_pct
)
SELECT achievement_month, rm_id, branch_id, region, rm_grade, actual_casa_amount, actual_loan_amount,
       actual_cards, actual_insurance, product_mix_score, attainment_pct,
       -- Target incentive is 0.15% of the combined target; the slab sets the multiple. A band that needs
       -- the product-mix gate and fails it pays half.
       round((target_casa_amount + target_loan_amount) * 0.0015 * payout
             * CASE WHEN gate_required AND product_mix_score < gate_min THEN 0.5 ELSE 1 END, 2) AS incentive_earned,
       NOT (gate_required AND product_mix_score < gate_min) AS quality_gate_passed,
       (gate_required AND product_mix_score < gate_min) AND payout >= 1.0 AS clawback_flag
FROM slabbed;

-- ============================================================ referential integrity
-- Rows that parsed but point at something the bank does not hold. Kept, with the reason, rather than
-- vanishing in an inner join.
CREATE OR REFRESH MATERIALIZED VIEW quarantine_orphans
COMMENT 'Rows that passed the format rules but reference something that does not exist: a contact on a loan the bank does not hold, a complaint with an unknown category, a loan with a product the bank does not sell, or a record for an unknown branch.'
AS
SELECT 'collections_activity' AS entity, a.activity_id AS record_id, 'unknown loan account' AS reason,
       a._source_path, a.source_system
FROM silver_collections_activity a
LEFT ANTI JOIN core_loan_accounts l ON l.loan_account_id = a.loan_account_id
UNION ALL
SELECT 'complaints', c.complaint_id,
       CASE WHEN k.category_code IS NULL THEN 'unknown complaint category' ELSE 'unknown branch' END,
       c._source_path, 'crm'
FROM (SELECT * FROM silver_complaints
      QUALIFY row_number() OVER (PARTITION BY complaint_id ORDER BY _ingested_at, _source_path) = 1) c
LEFT JOIN core_complaint_categories k ON k.category_code = c.category_code
LEFT JOIN core_branch_master b ON b.branch_id = c.branch_id
WHERE k.category_code IS NULL OR b.branch_id IS NULL
UNION ALL
SELECT 'loan_accounts', l.loan_account_id,
       CASE WHEN p.product_code IS NULL THEN 'unknown product code' ELSE 'unknown branch' END,
       l._source_path, 'los'
FROM core_loans_typed l
LEFT JOIN core_product_master p ON p.product_code = l.product_code
LEFT JOIN core_branch_master b ON b.branch_id = l.branch_id
WHERE p.product_code IS NULL OR b.branch_id IS NULL
UNION ALL
SELECT 'upi_disputes', u.dispute_id, 'unknown branch', u._source_path, 'upi_switch'
FROM silver_upi_disputes u
LEFT ANTI JOIN core_branch_master b ON b.branch_id = u.branch_id;
