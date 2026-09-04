-- Guardrail policies — the bank's controls, expressed as data.
--
-- Ten action types across the three domains. Between them they exercise every rung of the ladder:
-- two are safe enough to auto-execute (L4), six need a named human role, and two carry conduct
-- controls that are VERIFIED AGAINST UNITY CATALOG rather than trusted from the model's payload.
--
-- On `legal_basis`: the control is ours, the citation is the bank's. The text below names the
-- regulation each rule implements so a blocked action can explain itself, but the bank's compliance
-- function must confirm the exact circular references before this wording is used in production.
-- That division is deliberate — we ship the enforceable control, they own the legal text.

SET search_path TO ${LAKEBASE_SCHEMA};

INSERT INTO action_policies (
    action_type, domain, description,
    max_amount_inr, allowed_regions,
    requires_approval, approver_role, max_autonomy_level,
    rbi_conduct_hours, requires_agent_certification, blocked_by_open_grievance,
    min_dpd_days, max_contacts_per_day,
    legal_basis
) VALUES

-- ===================== COLLECTIONS & RECOVERY =====================

-- The headline control. A field visit is the most intrusive thing this system can cause to happen to
-- a customer, so it carries four independent checks and every one is grounded in governed data.
('schedule_field_visit', 'COLLECTIONS',
 'Dispatch a certified recovery agent to a borrower''s address.',
 NULL, NULL,
 TRUE, 'Collections Manager', 2,
 TRUE, TRUE, TRUE,
 60, 1,
 'RBI Fair Practices Code and the directions on outsourcing of financial services: recovery agents must not contact a borrower before 08:00 or after 19:00 local time, must be trained and certified before deployment, and recovery pressure must not continue while the customer''s grievance is open.'),

-- Agency allocation moves a whole tranche of accounts, so it is capped by portfolio value.
('assign_recovery_agency', 'COLLECTIONS',
 'Allocate a set of delinquent accounts to an external recovery agency.',
 50000000.00, NULL,
 TRUE, 'Collections Head', 2,
 FALSE, TRUE, FALSE,
 30, NULL,
 'RBI directions on outsourcing of financial services — the bank remains responsible for the conduct of its agents, so only certified agencies may be allocated accounts.'),

-- Recording what a customer said they will pay changes nothing and helps everyone. Safe at L4:
-- this is the action type that shows autonomy is a per-action decision, not a global switch.
('record_ptp', 'COLLECTIONS',
 'Record a promise-to-pay captured during a customer conversation.',
 NULL, NULL,
 FALSE, NULL, 4,
 FALSE, FALSE, FALSE,
 NULL, NULL,
 'Record-keeping only — no customer impact, no financial effect.'),

-- One-time settlement. Capped, and only in the regions where the scheme is board-approved.
('offer_settlement', 'COLLECTIONS',
 'Offer a one-time settlement or waiver on a delinquent account.',
 500000.00, ARRAY['West','Central'],
 TRUE, 'Credit Committee', 1,
 FALSE, FALSE, FALSE,
 90, NULL,
 'Board-approved one-time settlement policy — currently sanctioned only for the West and Central microfinance and commercial-vehicle portfolios. Waivers are a credit decision reserved to the Credit Committee.'),

-- ===================== SERVICE & GRIEVANCE =====================

('escalate_to_ombudsman', 'GRIEVANCE',
 'Refer an unresolved complaint to the Banking Ombudsman.',
 NULL, NULL,
 TRUE, 'Principal Nodal Officer', 1,
 FALSE, FALSE, FALSE,
 NULL, NULL,
 'Reserve Bank – Integrated Ombudsman Scheme: a referral is made by the bank''s Principal Nodal Officer, who owns the bank''s position in the proceeding.'),

('issue_provisional_credit', 'GRIEVANCE',
 'Credit a disputed UPI or card transaction back to the customer pending investigation.',
 25000.00, NULL,
 TRUE, 'Disputes Manager', 3,
 FALSE, FALSE, FALSE,
 NULL, NULL,
 'RBI harmonisation of turn-around time and customer compensation for failed transactions: provisional credit is due within the prescribed TAT, and compensation accrues per day of delay beyond it.'),

('waive_fee', 'GRIEVANCE',
 'Reverse a fee or charge as service redress.',
 10000.00, NULL,
 TRUE, 'Branch Manager', 3,
 FALSE, FALSE, FALSE,
 NULL, NULL,
 'Customer service policy — fee reversals are a financial concession and require branch authority.'),

-- The document-generation lane: the agent drafts the letter, a human signs it out.
('dispatch_customer_letter', 'GRIEVANCE',
 'Generate and send a resolution or acknowledgement letter to a customer.',
 NULL, NULL,
 TRUE, 'Service Manager', 2,
 FALSE, FALSE, FALSE,
 NULL, NULL,
 'Integrated Ombudsman Scheme requires a written, reasoned reply to the complainant; the signing authority is a named bank officer, never an automated system.'),

-- ===================== RM PERFORMANCE & INCENTIVES =====================

-- Deliberately gated hard. This action affects an employee's pay, so it cannot be automated at any
-- level and it goes to Compensation rather than to the RM's own line manager.
('hold_incentive_payout', 'RM',
 'Withhold a clawback-flagged incentive payout pending review.',
 NULL, NULL,
 TRUE, 'HR Compensation', 1,
 FALSE, FALSE, FALSE,
 NULL, NULL,
 'Employment and compensation policy — an adverse pay action requires human review by Compensation, independent of the employee''s reporting line. Never auto-approved.'),

('open_coaching_case', 'RM',
 'Open a coaching or product-mix review case for a relationship manager.',
 NULL, NULL,
 FALSE, NULL, 4,
 FALSE, FALSE, FALSE,
 NULL, NULL,
 'Development action with no pay or customer impact.')

ON CONFLICT (action_type) DO UPDATE SET
    domain                       = EXCLUDED.domain,
    description                  = EXCLUDED.description,
    max_amount_inr               = EXCLUDED.max_amount_inr,
    allowed_regions              = EXCLUDED.allowed_regions,
    requires_approval            = EXCLUDED.requires_approval,
    approver_role                = EXCLUDED.approver_role,
    max_autonomy_level           = EXCLUDED.max_autonomy_level,
    rbi_conduct_hours            = EXCLUDED.rbi_conduct_hours,
    requires_agent_certification = EXCLUDED.requires_agent_certification,
    blocked_by_open_grievance    = EXCLUDED.blocked_by_open_grievance,
    min_dpd_days                 = EXCLUDED.min_dpd_days,
    max_contacts_per_day         = EXCLUDED.max_contacts_per_day,
    legal_basis                  = EXCLUDED.legal_basis;
