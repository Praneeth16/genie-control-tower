-- Who may approve what.
--
-- action_policies names an `approver_role` for every gated action. Recording that name without
-- checking it is theatre: the queue would show "requires Collections Manager" while accepting a click
-- from anyone who could reach the URL. This table is the directory the check reads.
--
-- In production this is a SCIM group membership or an entitlement from the bank's IAM, and the check
-- becomes IS_ACCOUNT_GROUP_MEMBER. A table is used here because the workshop workspace has no
-- the bank groups to bind to, and because a table makes the control visible and auditable in the demo:
-- you can query who could have approved a given action, which is the question an auditor asks.

SET search_path TO ${LAKEBASE_SCHEMA};

CREATE TABLE IF NOT EXISTS approver_roles (
    principal   TEXT NOT NULL,
    role        TEXT NOT NULL,
    granted_by  TEXT,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal, role)
);

COMMENT ON TABLE approver_roles IS
  'Maps a person to the approval roles they hold. Read by the action plane before any approval is accepted, so an approval is refused unless the approver actually holds the role the policy names.';

-- The workshop presenter holds every role, so a single signed-in demo user can walk the whole ladder.
-- The two role-less entries exist to DEMONSTRATE refusal: they are real principals in the directory
-- who legitimately hold no approval authority.
INSERT INTO approver_roles (principal, role, granted_by) VALUES
    ('${ADMIN_PRINCIPAL}', 'Collections Manager',      'workshop-setup'),
    ('${ADMIN_PRINCIPAL}', 'Collections Head',         'workshop-setup'),
    ('${ADMIN_PRINCIPAL}', 'Credit Committee',         'workshop-setup'),
    ('${ADMIN_PRINCIPAL}', 'Principal Nodal Officer',  'workshop-setup'),
    ('${ADMIN_PRINCIPAL}', 'Disputes Manager',         'workshop-setup'),
    ('${ADMIN_PRINCIPAL}', 'Branch Manager',           'workshop-setup'),
    ('${ADMIN_PRINCIPAL}', 'Service Manager',          'workshop-setup'),
    ('${ADMIN_PRINCIPAL}', 'HR Compensation',          'workshop-setup'),
    -- A collections manager who may dispatch a field visit but may NOT touch anyone's pay.
    ('collections.manager@bank.example', 'Collections Manager',  'workshop-setup'),
    -- A branch manager who may reverse a fee but may not refer to the Ombudsman.
    ('branch.manager@bank.example',      'Branch Manager',       'workshop-setup')
ON CONFLICT (principal, role) DO NOTHING;
