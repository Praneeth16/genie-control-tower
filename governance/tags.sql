-- Classification tags on the governed gold tables. Runs AFTER the pipeline, on every cycle, because the
-- tables are pipeline-owned and tags are re-asserted idempotently rather than trusted to survive a full
-- refresh. Placeholders: ${CATALOG}, ${SCHEMA}.
--
-- ===========================================================================
-- Tags are the attribute layer: tagging a column documents its classification and lets a single
-- tag-driven policy cover tables nobody has created yet.
--
-- Worth showing the room: this metastore ENFORCES a tag policy, so tag values are not free text.
-- Probing it returned the permitted vocabulary:
--     domain              -> finance | sales | supply_chain | quality | hr | operations
--     data_classification -> u-nnpi | cui | pii
--     pii                 -> ssn | address
-- An attempt to write `domain = 'collections'` is REJECTED by Unity Catalog. That is ABAC working
-- as intended: the taxonomy is governed centrally, so a team cannot invent its own classification
-- and quietly fall outside the policies that key on it. We therefore map our domains onto the
-- approved vocabulary rather than inventing values.
--
-- Field-guide gotcha to state on the slide: UC tags are NOT inherited down the hierarchy. A tag on
-- the schema does not reach its tables. Tag at the level you actually query and certify, and audit
-- for drift — a table that silently loses its classification tag also loses any policy keyed on it.

-- PII columns: classified `pii` under the governed taxonomy. These are the same columns the masks
-- declared in pipeline/04_gold.sql protect, so the tag documents the intent and the mask enforces it.
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.loan_accounts         ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaints            ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaints            ALTER COLUMN complaint_text SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.upi_disputes          ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.chargebacks           ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.customer_portfolio    ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.product_holdings      ALTER COLUMN customer_id    SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.recovery_agents       ALTER COLUMN agent_name     SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.relationship_managers ALTER COLUMN rm_name        SET TAGS ('data_classification' = 'pii');

-- Non-PII business columns, classified as unclassified-non-NPI so the absence of a tag never has
-- to be read as "nobody looked at this yet".
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.delinquency_monthly ALTER COLUMN outstanding_principal SET TAGS ('data_classification' = 'u-nnpi');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.rm_achievement      ALTER COLUMN incentive_earned      SET TAGS ('data_classification' = 'cui');

-- Domain tags at table level, mapped onto the governed vocabulary:
--   collections + grievance -> operations
--   RM performance          -> sales
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.delinquency_monthly   SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.loan_accounts         SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.collections_activity  SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.recovery_agents       SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.repayment_schedule    SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaints            SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.sla_tracker           SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaint_categories  SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.upi_disputes          SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.chargebacks           SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.rm_achievement        SET TAGS ('domain' = 'sales');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.rm_targets            SET TAGS ('domain' = 'sales');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.relationship_managers SET TAGS ('domain' = 'sales');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.incentive_slabs       SET TAGS ('domain' = 'sales');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.customer_portfolio    SET TAGS ('domain' = 'sales');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.product_holdings      SET TAGS ('domain' = 'sales');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.branch_master         SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.product_master        SET TAGS ('domain' = 'operations');

-- Tables added with the pipeline.
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaint_documents   ALTER COLUMN document_text SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.collections_priority  ALTER COLUMN customer_id   SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaint_ai_triage   ALTER COLUMN summary       SET TAGS ('data_classification' = 'pii');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaint_documents   SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.collections_priority  SET TAGS ('domain' = 'operations');
ALTER MATERIALIZED VIEW ${CATALOG}.${SCHEMA}.complaint_ai_triage   SET TAGS ('domain' = 'operations');
