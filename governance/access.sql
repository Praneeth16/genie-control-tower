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

-- Read-only access. SELECT and EXECUTE on the schema; the row filters and masks decide what each one sees.
-- Nobody here is granted MODIFY: writes happen through the app's action plane, never through SQL.
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${CRO}`;
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${COLLECTIONS_HEAD}`;
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${GRIEVANCE_OFFICER}`;
GRANT USE CATALOG ON CATALOG ${CATALOG} TO `${AUDITOR}`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${CRO}`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${COLLECTIONS_HEAD}`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${GRIEVANCE_OFFICER}`;
GRANT USE SCHEMA, SELECT, EXECUTE ON SCHEMA ${CATALOG}.${SCHEMA} TO `${AUDITOR}`;
