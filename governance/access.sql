-- The personas, as entitlement rows and least-privilege grants. Runs after policies.sql.
--
-- Each persona is a service principal so the evidence can run the SAME query AS each of them (a job
-- task with run_as) and show what each one actually gets back. In a bank these would be account groups
-- synced from the identity provider; the entitlements table accepts either, unchanged.
--
--   Chief Risk Officer       every region, aggregates; identifiers pseudonymised, no free text
--   Head of Collections      West and Central only (the two regions under stress); pseudonymised
--   Grievance officer        every region; reads complaint text and letters; identifiers pseudonymised
--   Internal auditor         everything, unmasked
--
-- Placeholders: ${CATALOG}, ${SCHEMA}, ${CRO}, ${COLLECTIONS_HEAD}, ${GRIEVANCE_OFFICER}, ${AUDITOR}.

MERGE INTO ${CATALOG}.${SCHEMA}.entitlements t
USING (
  SELECT * FROM VALUES
    ('${CRO}',               'Chief Risk Officer',   'ALL',     FALSE, FALSE),
    ('${COLLECTIONS_HEAD}',  'Head of Collections',  'West',    FALSE, FALSE),
    ('${COLLECTIONS_HEAD}',  'Head of Collections',  'Central', FALSE, FALSE),
    ('${GRIEVANCE_OFFICER}', 'Grievance officer',    'ALL',     FALSE, TRUE),
    ('${AUDITOR}',           'Internal auditor',     'ALL',     TRUE,  TRUE)
  AS s(principal, persona, region, can_see_pii, can_see_complaint_text)
) s
ON t.principal = s.principal AND t.region = s.region
WHEN MATCHED THEN UPDATE SET persona = s.persona, can_see_pii = s.can_see_pii,
                             can_see_complaint_text = s.can_see_complaint_text
WHEN NOT MATCHED THEN INSERT (principal, persona, region, can_see_pii, can_see_complaint_text, granted_by, granted_at)
  VALUES (s.principal, s.persona, s.region, s.can_see_pii, s.can_see_complaint_text, 'setup', current_timestamp());

-- Read-only access. Catalog and schema USE, and EXECUTE on the policy and control functions. SELECT is NOT
-- granted on the schema: the schema also holds bronze, silver and quarantine tables, which carry raw
-- customer identifiers and letter text with no row filter or mask. Personas get SELECT only on the
-- governed tables, table by table, in governance/grants.sql once the pipeline has created them.
-- Nobody here is granted MODIFY: writes happen through the app's action plane, never through SQL.
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${CRO}`;
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${COLLECTIONS_HEAD}`;
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${GRIEVANCE_OFFICER}`;
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${AUDITOR}`;
GRANT USE SCHEMA, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${CRO}`;
GRANT USE SCHEMA, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${COLLECTIONS_HEAD}`;
GRANT USE SCHEMA, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${GRIEVANCE_OFFICER}`;
GRANT USE SCHEMA, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${AUDITOR}`;
-- An earlier version granted SELECT on the whole schema; remove it.
REVOKE SELECT ON SCHEMA ${CATALOG}.${SCHEMA} FROM `${CRO}`;
REVOKE SELECT ON SCHEMA ${CATALOG}.${SCHEMA} FROM `${COLLECTIONS_HEAD}`;
REVOKE SELECT ON SCHEMA ${CATALOG}.${SCHEMA} FROM `${GRIEVANCE_OFFICER}`;
REVOKE SELECT ON SCHEMA ${CATALOG}.${SCHEMA} FROM `${AUDITOR}`;
