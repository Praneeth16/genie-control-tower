-- INTELLIGENCE, inside the data flow: an explainable priority score, and an LLM that reads the letters.
--
-- The split of responsibility is deliberate:
--   * WHO to work first is a points score with named components, stored on every row with the reasons.
--     A Head of Collections can argue with "+35 because SMA-2"; nobody can argue with a model's 0.73.
--   * The LLM READS what customers wrote (letters a person would otherwise read one by one) and turns
--     it into fields: the RBI ground, whether recovery-agent misconduct is alleged, how urgent. It
--     classifies and summarises; it decides nothing. Its output feeds the score's conduct flags and the
--     grievance agent, and its accuracy is measured against the ground recorded on each complaint.
--
-- Pipeline configuration: ${ai_model}, ${triage_prompt_version}

-- ============================================================ letter triage (ai_query, incremental)
-- A streaming table, so each letter is read by the model exactly once, when it lands. Re-triaging
-- everything under a new prompt is a selective full refresh of this one table.
--
-- Only the letter BODY is sent: the header lines (complaint id, branch city, product) are stripped, so
-- the model classifies what the customer wrote and nothing else.
CREATE OR REFRESH PRIVATE STREAMING TABLE core_letter_triage AS
WITH letters AS (
  SELECT regexp_extract(_file_name, '^(CM[0-9]+)', 1) AS complaint_id, _source_path, _ingested_at,
         trim(regexp_extract(letter_text, '(?s)To the Grievance Redressal Officer,(.*?)Yours faithfully', 1)) AS body
  FROM STREAM(bronze_correspondence)
),
scored AS (
  SELECT *,
    ai_query(
      '${ai_model}',
      concat(
        CASE '${triage_prompt_version}'
          WHEN 'v1' THEN
            'You triage customer complaint letters for the grievance desk of an Indian retail bank. '
            'Classify the letter using ONLY what it says. Do not guess facts that are not in the letter.\n'
            'rbi_ground: the RBI Integrated Ombudsman Scheme ground that best fits.\n'
            'alleges_conduct_breach: true only if the customer describes misconduct by a recovery agent.\n'
            'breach_types: the kinds of misconduct described, empty if none.\n'
            'urgency: high if the customer describes harassment, threats, disclosure to third parties, or money lost and not returned; medium if a service failure is ongoing; otherwise low.\n'
            'summary: one sentence, no names, no account numbers.\n\nLETTER:\n'
          WHEN 'v2' THEN
            'You triage customer complaint letters for the grievance desk of an Indian retail bank. '
            'Classify the letter using ONLY what it says. Do not guess facts that are not in the letter.\n'
            'rbi_ground: choose by what went wrong, using these definitions:\n'
            '  Payment systems: a UPI, NEFT, IMPS, standing-instruction or ATM transaction failed, was debited twice, or was not reversed, including an ATM that kept the card or did not dispense cash.\n'
            '  Cards: a credit or debit card transaction is disputed (duplicate charge, unrecognised transaction, unrequested EMI conversion).\n'
            '  Loans and advances: servicing of a loan (foreclosure statement, no-objection certificate, EMI after closure).\n'
            '  Deposit accounts: a savings, salary or fixed deposit account was operated wrongly (premature closure, wrong interest, penalty on an exempt account).\n'
            '  Levy of charges: a fee or charge was levied without disclosure or despite a waiver, on any product, where the charge itself is the complaint.\n'
            '  Mis-selling: a product was sold as compulsory, mis-described, or added without consent.\n'
            '  Recovery agents: the conduct of agents collecting a debt.\n'
            '  Other: KYC or re-KYC, documents, an address change, or an account restricted while documents are pending, and anything not above.\n'
            'alleges_conduct_breach: true only if the customer describes misconduct by a recovery agent: contact before 08:00 or after 19:00, threats or abuse, disclosure of the debt to third parties, refusal to identify, or repeated visits after a stated hardship.\n'
            'breach_types: the kinds of misconduct described, empty if none.\n'
            'urgency: high if the customer describes harassment, threats, disclosure to third parties, or money lost and not returned; medium if a service failure is ongoing; otherwise low.\n'
            'summary: one sentence, no names, no account numbers.\n\nLETTER:\n'
        END,
        body),
      responseFormat => '{"type":"json_schema","json_schema":{"name":"letter_triage","strict":true,"schema":{"type":"object","additionalProperties":false,"required":["rbi_ground","alleges_conduct_breach","breach_types","urgency","summary"],"properties":{"rbi_ground":{"type":"string","enum":["Payment systems","Cards","Loans and advances","Deposit accounts","Levy of charges","Mis-selling","Recovery agents","Other"]},"alleges_conduct_breach":{"type":"boolean"},"breach_types":{"type":"array","items":{"type":"string","enum":["out_of_hours_contact","threats_or_abuse","third_party_disclosure","no_identification","pressure_after_hardship"]}},"urgency":{"type":"string","enum":["high","medium","low"]},"summary":{"type":"string"}}}}}',
      modelParameters => named_struct('temperature', 0.0),
      failOnError => false
    ) AS response
  FROM letters
)
SELECT complaint_id, _source_path, _ingested_at, body,
       from_json(response.result,
         'rbi_ground STRING, alleges_conduct_breach BOOLEAN, breach_types ARRAY<STRING>, urgency STRING, summary STRING') AS triage,
       nullif(response.errorMessage, '') AS error,
       '${ai_model}' AS model, '${triage_prompt_version}' AS prompt_version, current_timestamp() AS triaged_at
FROM scored;

CREATE OR REFRESH MATERIALIZED VIEW complaint_ai_triage (
  complaint_id            STRING        COMMENT 'Complaint the letter belongs to. Join to complaints.',
  received_date           DATE          COMMENT 'Date the complaint was received.',
  branch_id               STRING        COMMENT 'Branch the complaint is attributed to.',
  region                  STRING        COMMENT 'Region of the branch.',
  predicted_rbi_ground    STRING        COMMENT 'RBI ground of complaint as read from the customer\'s letter by the AI triage step. Compare with complaints.rbi_category, which is the ground recorded by the grievance desk.',
  alleges_conduct_breach  BOOLEAN       COMMENT 'TRUE when the letter describes recovery-agent misconduct, as read by the AI triage step. A signal for review, not a finding.',
  breach_types            ARRAY<STRING> COMMENT 'Kinds of misconduct described: out_of_hours_contact, threats_or_abuse, third_party_disclosure, no_identification, pressure_after_hardship.',
  urgency                 STRING        COMMENT 'high, medium or low, as read from the letter.',
  summary                 STRING        MASK ${catalog}.${schema}.mask_complaint_text COMMENT 'One-sentence AI summary of the letter. Redacted like the letter itself for callers not cleared to read free text.',
  model                   STRING        COMMENT 'Model endpoint that produced the triage.',
  prompt_version          STRING        COMMENT 'Prompt version used.',
  triaged_at              TIMESTAMP     COMMENT 'When the letter was triaged.',
  error                   STRING        COMMENT 'Model error, when the call failed. Failed rows are kept, never silently dropped.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'AI triage of every customer complaint letter: the RBI ground, whether recovery-agent misconduct is alleged, urgency and a one-line summary. Produced inside the pipeline by ai_query with a fixed JSON schema; evaluated against the recorded ground in ai_eval_* tables.'
AS SELECT t.complaint_id, c.received_date, c.branch_id, c.region,
          t.triage.rbi_ground AS predicted_rbi_ground, t.triage.alleges_conduct_breach, t.triage.breach_types, t.triage.urgency,
          t.triage.summary, t.model, t.prompt_version, t.triaged_at, t.error
FROM core_letter_triage t
JOIN core_complaints c ON c.complaint_id = t.complaint_id;

-- ============================================================ the collections priority score
CREATE OR REFRESH MATERIALIZED VIEW collections_priority (
  loan_account_id                STRING        COMMENT 'Loan account, primary key. Join to loan_accounts.',
  customer_id                    STRING        MASK ${catalog}.${schema}.mask_customer_id COMMENT 'Borrower, or a CU- pseudonym.',
  product_code                   STRING        COMMENT 'Product code.',
  branch_id                      STRING        COMMENT 'Branch code.',
  region                         STRING        COMMENT 'Region.',
  snapshot_month                 DATE          COMMENT 'Month-end snapshot the score is computed from (the latest available).',
  dpd_days                       INT           COMMENT 'Days past due at that snapshot.',
  dpd_bucket                     STRING        COMMENT 'Regulatory ageing bucket.',
  is_npa                         BOOLEAN       COMMENT 'TRUE when more than 90 days past due.',
  outstanding_principal          DOUBLE        COMMENT 'Outstanding principal in INR.',
  overdue_amount                 DOUBLE        COMMENT 'Overdue amount in INR.',
  forward_rolls_3m               BIGINT        COMMENT 'Months in the last three in which the account rolled into a worse bucket.',
  contacts_90d                   BIGINT        COMMENT 'Contact attempts in the 90 days to the snapshot month end.',
  promises_90d                   BIGINT        COMMENT 'Promises to pay given in those 90 days.',
  payments_90d                   BIGINT        COMMENT 'Payments or part-payments collected in those 90 days.',
  out_of_hours_contacts_90d      BIGINT        COMMENT 'Contacts outside 08:00 to 19:00 IST in those 90 days. A conduct risk on this account.',
  uncertified_agent_contacts_90d BIGINT        COMMENT 'Contacts by an agent who was inactive, uncertified or whose certification had lapsed on the day. A conduct risk on this account.',
  last_contact_date              DATE          COMMENT 'Most recent contact attempt.',
  open_grievance                 BOOLEAN       COMMENT 'TRUE when the borrower has an open complaint or one escalated to the Ombudsman. Recovery contact must be suspended while it is open.',
  ai_alleged_conduct_breach      BOOLEAN       COMMENT 'TRUE when one of the borrower\'s letters alleges recovery-agent misconduct, as read by the AI triage step.',
  dpd_points                     INT           COMMENT 'Score component: 10 SMA-0, 20 SMA-1, 35 SMA-2, 50 NPA.',
  roll_points                    INT           COMMENT 'Score component: 10 per forward roll in the last three months.',
  exposure_points                INT           COMMENT 'Score component: 15 for INR 10 lakh or more outstanding, 8 for INR 2 lakh or more, otherwise 3.',
  promise_points                 INT           COMMENT 'Score component: 5 per promise to pay not matched by a payment in 90 days, up to 15.',
  priority_score                 INT           COMMENT 'Sum of the four components, 0 to 110. Higher means work first.',
  priority_rank                  INT           COMMENT 'Rank by priority_score, then outstanding principal. 1 is the first account to work.',
  drivers                        ARRAY<STRING> COMMENT 'The components that scored, in words, e.g. "Days past due 72 (3-SMA2 (61-90)): +35".',
  conduct_flags                  ARRAY<STRING> COMMENT 'Conduct reasons that change HOW the account may be worked, regardless of score.',
  recommended_treatment          STRING        COMMENT 'Rule-based next treatment. Conduct rules come first: an open grievance always means hold.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Collections worklist: every delinquent account at the latest month end, ranked by an explainable points score whose components and reasons are stored on the row, with the conduct flags that decide how it may be worked. Synced to Lakebase as the case queue the collections team acts on.'
AS
WITH latest AS (SELECT max(snapshot_month) AS m FROM core_delinquency),
cur AS (
  SELECT d.* FROM core_delinquency d JOIN latest ON d.snapshot_month = latest.m WHERE d.dpd_days > 0
),
rolls AS (
  SELECT d.loan_account_id, count_if(d.roll_direction = 'forward') AS forward_rolls_3m
  FROM core_delinquency d JOIN latest ON d.snapshot_month > add_months(latest.m, -3)
  GROUP BY 1
),
act AS (
  SELECT a.loan_account_id,
         count(*) AS contacts_90d,
         count_if(a.outcome = 'Contacted - PTP') AS promises_90d,
         count_if(a.outcome IN ('Paid', 'Partial Payment')) AS payments_90d,
         count_if(NOT a.within_rbi_hours) AS out_of_hours_contacts_90d,
         count_if(NOT coalesce(g.active_flag AND g.rbi_conduct_certified AND g.certification_expiry >= a.activity_date, FALSE))
           AS uncertified_agent_contacts_90d,
         max(a.activity_date) AS last_contact_date
  FROM core_collections_activity a
  CROSS JOIN latest
  LEFT JOIN core_recovery_agents g ON g.agent_id = a.agent_id
  WHERE a.activity_date > date_sub(last_day(latest.m), 90) AND a.activity_date <= last_day(latest.m)
  GROUP BY 1
),
griev AS (
  SELECT customer_id, bool_or(status = 'Open' OR escalated_to_ombudsman) AS open_grievance
  FROM core_complaints GROUP BY 1
),
ai AS (
  SELECT c.customer_id, bool_or(t.triage.alleges_conduct_breach) AS ai_alleged_conduct_breach
  FROM core_letter_triage t JOIN core_complaints c ON c.complaint_id = t.complaint_id
  GROUP BY 1
),
base AS (
  SELECT cur.loan_account_id, l.customer_id, cur.product_code, cur.branch_id, cur.region, cur.snapshot_month,
         cur.dpd_days, cur.dpd_bucket, cur.is_npa, cur.outstanding_principal, cur.overdue_amount,
         coalesce(r.forward_rolls_3m, 0) AS forward_rolls_3m,
         coalesce(a.contacts_90d, 0) AS contacts_90d, coalesce(a.promises_90d, 0) AS promises_90d,
         coalesce(a.payments_90d, 0) AS payments_90d,
         coalesce(a.out_of_hours_contacts_90d, 0) AS out_of_hours_contacts_90d,
         coalesce(a.uncertified_agent_contacts_90d, 0) AS uncertified_agent_contacts_90d,
         a.last_contact_date,
         coalesce(g.open_grievance, FALSE) AS open_grievance,
         coalesce(ai.ai_alleged_conduct_breach, FALSE) AS ai_alleged_conduct_breach
  FROM cur
  JOIN core_loan_accounts l ON l.loan_account_id = cur.loan_account_id
  LEFT JOIN rolls r ON r.loan_account_id = cur.loan_account_id
  LEFT JOIN act a ON a.loan_account_id = cur.loan_account_id
  LEFT JOIN griev g ON g.customer_id = l.customer_id
  LEFT JOIN ai ON ai.customer_id = l.customer_id
),
points AS (
  SELECT *,
    CASE dpd_bucket WHEN '1-SMA0 (1-30)' THEN 10 WHEN '2-SMA1 (31-60)' THEN 20
                    WHEN '3-SMA2 (61-90)' THEN 35 ELSE 50 END AS dpd_points,
    CAST(least(forward_rolls_3m, 3) * 10 AS INT) AS roll_points,
    CASE WHEN outstanding_principal >= 1000000 THEN 15 WHEN outstanding_principal >= 200000 THEN 8 ELSE 3 END
      AS exposure_points,
    CAST(least(greatest(promises_90d - payments_90d, 0), 3) * 5 AS INT) AS promise_points
  FROM base
)
SELECT loan_account_id, customer_id, product_code, branch_id, region, snapshot_month, dpd_days, dpd_bucket,
       is_npa, outstanding_principal, overdue_amount, forward_rolls_3m, contacts_90d, promises_90d,
       payments_90d, out_of_hours_contacts_90d, uncertified_agent_contacts_90d, last_contact_date,
       open_grievance, ai_alleged_conduct_breach,
       dpd_points, roll_points, exposure_points, promise_points,
       dpd_points + roll_points + exposure_points + promise_points AS priority_score,
       CAST(row_number() OVER (ORDER BY dpd_points + roll_points + exposure_points + promise_points DESC,
                                        outstanding_principal DESC, loan_account_id) AS INT) AS priority_rank,
       filter(array(
         concat('Days past due ', dpd_days, ' (', dpd_bucket, '): +', dpd_points),
         CASE WHEN roll_points > 0 THEN concat('Rolled to a worse bucket in ', forward_rolls_3m, ' of the last 3 months: +', roll_points) END,
         concat('Outstanding INR ', format_number(outstanding_principal, 0), ': +', exposure_points),
         CASE WHEN promise_points > 0 THEN concat(promises_90d - payments_90d, ' promise(s) to pay not kept in 90 days: +', promise_points) END
       ), x -> x IS NOT NULL) AS drivers,
       filter(array(
         CASE WHEN open_grievance THEN 'Open grievance: recovery contact must be suspended' END,
         CASE WHEN ai_alleged_conduct_breach THEN 'Borrower letter alleges recovery-agent misconduct (AI-read)' END,
         CASE WHEN out_of_hours_contacts_90d > 0 THEN concat(out_of_hours_contacts_90d, ' contact(s) outside 08:00-19:00 IST in 90 days') END,
         CASE WHEN uncertified_agent_contacts_90d > 0 THEN concat(uncertified_agent_contacts_90d, ' contact(s) by an uncertified or lapsed agent in 90 days') END
       ), x -> x IS NOT NULL) AS conduct_flags,
       CASE
         WHEN open_grievance THEN 'Hold recovery contact until the grievance is closed'
         WHEN ai_alleged_conduct_breach OR out_of_hours_contacts_90d > 0 OR uncertified_agent_contacts_90d > 0
           THEN 'Reassign to a certified agency and review conduct'
         WHEN is_npa THEN 'Settlement or legal review'
         WHEN dpd_days > 60 THEN 'Field visit by a certified agent'
         ELSE 'Tele-calling and digital reminder'
       END AS recommended_treatment
FROM points;
