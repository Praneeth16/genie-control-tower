-- AI case briefs for the top of the collections worklist. Runs after the pipeline, in the cycle job.
--
-- The score decides the ORDER; this step only explains it in plain words and suggests one next action
-- for the collections officer, who decides. It sees the account's facts and nothing else: no customer
-- identifier, no name, no letter text. A brief is regenerated only when the account's facts or the
-- prompt change, so a rerun with nothing new costs nothing and every brief can be traced to the exact
-- facts it was written from.
--
-- The model's suggestion is checked afterwards (ai/evaluate.py) against the deterministic conduct rules
-- in collections_priority.recommended_treatment and by LLM judges from a different model family.
--
-- Placeholders: ${CATALOG}, ${SCHEMA}, ${AI_MODEL}, ${BRIEF_PROMPT_VERSION}, ${TOP_N}.

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.collections_case_brief (
  loan_account_id    STRING        COMMENT 'Loan account the brief is about.',
  region             STRING        COMMENT 'Region of the account, for the row filter.',
  snapshot_month     DATE          COMMENT 'Month-end the facts are from.',
  priority_rank      INT           COMMENT 'Rank on the worklist when the brief was written.',
  facts              STRING        COMMENT 'The exact facts given to the model, as JSON. No customer identifiers.',
  facts_hash         STRING        COMMENT 'Hash of facts and prompt version; a brief is regenerated only when this changes.',
  explanation        STRING        COMMENT 'Why the account is where it is on the list, in at most 60 words, from the facts only.',
  recommended_action STRING        COMMENT 'One suggested next action: hold_contact, assign_recovery_agency, offer_settlement, schedule_field_visit or tele_calling_reminder. A suggestion for the officer, never executed automatically.',
  facts_used         ARRAY<STRING> COMMENT 'Which facts the model says it relied on.',
  model              STRING        COMMENT 'Model endpoint.',
  prompt_version     STRING        COMMENT 'Prompt version.',
  error              STRING        COMMENT 'Model error, when the call failed.',
  briefed_at         TIMESTAMP     COMMENT 'When the brief was written.'
)
WITH ROW FILTER ${CATALOG}.${SCHEMA}.region_visible ON (region)
COMMENT 'AI-written case briefs for the top of the collections worklist, one per account and prompt version. Explanations and suggestions only; the officer decides and every action still goes through approval.';

MERGE INTO ${CATALOG}.${SCHEMA}.collections_case_brief t
USING (
  WITH top AS (
    SELECT loan_account_id, region, snapshot_month, priority_rank,
           to_json(named_struct(
             'product_code', product_code, 'region', region, 'snapshot_month', snapshot_month,
             'dpd_days', dpd_days, 'dpd_bucket', dpd_bucket, 'is_npa', is_npa,
             'outstanding_principal_inr', round(outstanding_principal, 0), 'overdue_amount_inr', round(overdue_amount, 0),
             'forward_rolls_last_3_months', forward_rolls_3m, 'contacts_90d', contacts_90d,
             'promises_to_pay_90d', promises_90d, 'payments_90d', payments_90d,
             'out_of_hours_contacts_90d', out_of_hours_contacts_90d,
             'uncertified_agent_contacts_90d', uncertified_agent_contacts_90d,
             'last_contact_date', last_contact_date, 'open_grievance', open_grievance,
             'letter_alleges_agent_misconduct', ai_alleged_conduct_breach,
             'priority_score', priority_score, 'priority_rank', priority_rank,
             'score_drivers', drivers, 'conduct_flags', conduct_flags)) AS facts
    FROM ${CATALOG}.${SCHEMA}.collections_priority
    WHERE priority_rank <= ${TOP_N}
  ),
  todo AS (
    SELECT top.*, sha2(concat(facts, '${BRIEF_PROMPT_VERSION}'), 256) AS facts_hash
    FROM top
    LEFT ANTI JOIN ${CATALOG}.${SCHEMA}.collections_case_brief b
      ON b.loan_account_id = top.loan_account_id AND b.prompt_version = '${BRIEF_PROMPT_VERSION}'
     AND b.facts_hash = sha2(concat(top.facts, '${BRIEF_PROMPT_VERSION}'), 256) AND b.error IS NULL
  ),
  gen AS (
    SELECT todo.*,
      ai_query('${AI_MODEL}',
        concat(
          CASE '${BRIEF_PROMPT_VERSION}'
            WHEN 'v1' THEN
              'You write case briefs for a collections officer at an Indian retail bank. '
              'Use ONLY the facts in the JSON below. Never invent people, amounts, dates, documents or events, '
              'and never state a number that is not in the facts.\n'
              'explanation: at most 60 words, plain English, saying why this account is at this position on the '
              'worklist and anything that limits how it may be worked.\n'
              'recommended_action: exactly one of the allowed values, the most appropriate next step.\n'
              'facts_used: the JSON keys you relied on.\n\nFACTS:\n'
            WHEN 'v2' THEN
              'You write case briefs for a collections officer at an Indian retail bank. '
              'Use ONLY the facts in the JSON below. Never invent people, amounts, dates, documents or events, '
              'and never state a number that is not in the facts.\n'
              'The bank\'s conduct rules come before recovery priority, in this order:\n'
              '  1. open_grievance true: recommend hold_contact. Recovery contact is suspended while a grievance is open.\n'
              '  2. otherwise, any out-of-hours or uncertified-agent contact, or a letter alleging agent misconduct: '
              'recommend assign_recovery_agency (move the account to a certified agency) and say why.\n'
              '  3. otherwise, NPA (more than 90 days past due): offer_settlement.\n'
              '  4. otherwise, more than 60 days past due: schedule_field_visit.\n'
              '  5. otherwise: tele_calling_reminder.\n'
              'explanation: two or three short sentences, at most 50 words, plain English, saying why this account is '
              'at this position on the worklist and which conduct rule, if any, limits how it may be worked. '
              'Quote amounts exactly as they appear in the facts, in INR, without converting to lakh or crore, '
              'and do no arithmetic on them.\n'
              'recommended_action: exactly one of the allowed values, following the rules above.\n'
              'facts_used: the JSON keys you relied on.\n\nFACTS:\n'
          END,
          facts),
        responseFormat => '{"type":"json_schema","json_schema":{"name":"case_brief","strict":true,"schema":{"type":"object","additionalProperties":false,"required":["explanation","recommended_action","facts_used"],"properties":{"explanation":{"type":"string"},"recommended_action":{"type":"string","enum":["hold_contact","assign_recovery_agency","offer_settlement","schedule_field_visit","tele_calling_reminder"]},"facts_used":{"type":"array","items":{"type":"string"}}}}}}',
        modelParameters => named_struct('temperature', 0.0),
        failOnError => false) AS response
    FROM todo
  )
  SELECT loan_account_id, region, snapshot_month, priority_rank, facts, facts_hash,
         from_json(response.result, 'explanation STRING, recommended_action STRING, facts_used ARRAY<STRING>') AS r,
         nullif(response.errorMessage, '') AS error
  FROM gen
) s
ON t.loan_account_id = s.loan_account_id AND t.prompt_version = '${BRIEF_PROMPT_VERSION}'
WHEN MATCHED THEN UPDATE SET
  region = s.region, snapshot_month = s.snapshot_month, priority_rank = s.priority_rank, facts = s.facts,
  facts_hash = s.facts_hash, explanation = s.r.explanation, recommended_action = s.r.recommended_action,
  facts_used = s.r.facts_used, model = '${AI_MODEL}', error = s.error, briefed_at = current_timestamp()
WHEN NOT MATCHED THEN INSERT (loan_account_id, region, snapshot_month, priority_rank, facts, facts_hash, explanation,
                              recommended_action, facts_used, model, prompt_version, error, briefed_at)
VALUES (s.loan_account_id, s.region, s.snapshot_month, s.priority_rank, s.facts, s.facts_hash, s.r.explanation,
        s.r.recommended_action, s.r.facts_used, '${AI_MODEL}', '${BRIEF_PROMPT_VERSION}', s.error, current_timestamp());
