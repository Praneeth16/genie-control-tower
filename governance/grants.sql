-- SELECT on the governed tables only, for one principal. Run after the pipeline (the cycle job's govern
-- task), once per persona. Each of these tables either carries a row filter and masks, or holds no
-- customer data (reference dimensions, completeness and quality summaries, AI evaluation metrics).
-- Bronze, silver, quarantine and the evaluation's per-record results are deliberately absent.
-- Placeholders: ${CATALOG}, ${SCHEMA}, ${PRINCIPAL}.
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.branch_master TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.product_master TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.loan_accounts TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.delinquency_monthly TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.collections_activity TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.recovery_agents TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.repayment_schedule TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.complaint_categories TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.complaints TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.upi_disputes TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.chargebacks TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.sla_tracker TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.relationship_managers TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.incentive_slabs TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.rm_targets TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.rm_achievement TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.customer_portfolio TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.product_holdings TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.complaint_documents TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.collections_priority TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.complaint_ai_triage TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.collections_case_brief TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.collections_case_status TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.recon_completeness TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.data_quality_summary TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.ai_eval_summary TO `${PRINCIPAL}`;
GRANT SELECT ON TABLE ${CATALOG}.${SCHEMA}.my_entitlements TO `${PRINCIPAL}`;
