-- GOLD: the governed tables people, Genie and the app query.
--
-- Same 18 table names the Genie agents, the dashboard, the app and the UC control functions were built
-- against, so nothing downstream had to change its SQL when the data stopped being loaded by hand.
--
-- Row filters and column masks are declared IN the definitions, not attached afterwards with ALTER. An
-- ALTER on a pipeline-owned table is lost on the next full refresh, and the table then comes back
-- ungoverned while looking perfectly healthy. Declared here, the policy is part of the table.
--
-- Every table and column carries a COMMENT in the business vocabulary a banker uses, with units. That is
-- the single highest-leverage accuracy lever for Genie: columns it cannot interpret are columns it guesses.

-- ============================================================ shared dimensions
CREATE OR REFRESH MATERIALIZED VIEW branch_master (
  branch_id      STRING COMMENT 'Branch code, primary key. Format BRnnn. Join to any fact table on branch_id.',
  branch_name    STRING COMMENT 'Human-readable branch name, e.g. "Solapur Rural".',
  city           STRING COMMENT 'City the branch is located in.',
  state          STRING COMMENT 'Indian state, e.g. Maharashtra, Madhya Pradesh.',
  region         STRING COMMENT 'Sales region. One of North, South, East, West, Central. Use this for regional roll-ups.',
  zone           STRING COMMENT 'Branch classification: Metro, Urban, Semi-Urban, or Rural. Rural and Semi-Urban carry most microfinance exposure.',
  opened_date    DATE   COMMENT 'Date the branch opened.',
  employee_count INT    COMMENT 'Number of staff at the branch.'
)
COMMENT 'Branch dimension. One row per bank branch, 18 synthetic branches across 5 regions. Join key for every fact table in this schema.'
AS SELECT * FROM core_branch_master;

CREATE OR REFRESH MATERIALIZED VIEW product_master (
  product_code STRING  COMMENT 'Product code, primary key. CV=Commercial Vehicle, PV=Passenger Vehicle, TW=Two Wheeler, MFI=Microfinance Group Loan, PL=Personal Loan, CC=Credit Card, HL=Home Loan, BL=Business Loan.',
  product_name STRING  COMMENT 'Full product name.',
  segment      STRING  COMMENT 'Business line: Vehicle Finance, Microfinance, Retail Unsecured, Cards, Mortgages, Business Banking.',
  is_secured   BOOLEAN COMMENT 'TRUE when the loan is secured by collateral. Microfinance, personal loans, cards and business loans are unsecured.'
)
COMMENT 'Lending and card product dimension. Join on product_code. Segment groups products into the bank business lines.'
AS SELECT * FROM core_product_master;

-- ============================================================ collections and recovery
CREATE OR REFRESH MATERIALIZED VIEW loan_accounts (
  loan_account_id       STRING  COMMENT 'Loan account number, primary key. Format LNnnnnnn.',
  customer_id           STRING  MASK ${catalog}.${schema}.mask_customer_id COMMENT 'Customer identifier. Format CUnnnnnn, or a CU- pseudonym for callers not cleared to see identifiers. Join to customer_portfolio to reach the relationship manager.',
  product_code          STRING  COMMENT 'Product code. Join to product_master. MFI is microfinance, CV is commercial vehicle.',
  branch_id             STRING  COMMENT 'Originating branch. Join to branch_master.',
  disbursed_date        DATE    COMMENT 'Date the loan was disbursed.',
  sanctioned_amount     DOUBLE  COMMENT 'Original sanctioned loan amount in INR. This is the amount approved at origination, NOT the current balance.',
  outstanding_principal DOUBLE  COMMENT 'Current outstanding principal in INR. USE THIS for exposure, book size, and portfolio value questions.',
  interest_rate         DOUBLE  COMMENT 'Annual interest rate as a percentage, e.g. 23.5 means 23.5 percent per annum.',
  tenure_months         INT     COMMENT 'Loan tenure in months. Zero for revolving products such as credit cards.',
  emi_amount            DOUBLE  COMMENT 'Monthly instalment (EMI) in INR. Zero for revolving products.',
  customer_segment      STRING  COMMENT 'Borrower segment, e.g. Rural Household (microfinance), Small Fleet Operator (commercial vehicle), Salaried, Self Employed, MSME.',
  is_restructured       BOOLEAN COMMENT 'TRUE when the loan has been restructured. Restructured accounts need separate treatment in delinquency analysis.',
  region                STRING  COMMENT 'Region of the originating branch, denormalised so regional questions need no join.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Loan account master. One row per loan account, 6,000 accounts. Current book position: use outstanding_principal, not sanctioned_amount, when asked about exposure or book size.'
AS SELECT * FROM core_loan_accounts;

CREATE OR REFRESH MATERIALIZED VIEW delinquency_monthly (
  snapshot_month        DATE    COMMENT 'Month-end snapshot date, always the first day of the month. Filter on this for point-in-time questions; the latest month is MAX(snapshot_month).',
  loan_account_id       STRING  COMMENT 'Loan account number. Join to loan_accounts.',
  product_code          STRING  COMMENT 'Product code, denormalised from loan_accounts so product filters need no join.',
  branch_id             STRING  COMMENT 'Branch code, denormalised from loan_accounts so branch filters need no join.',
  region                STRING  COMMENT 'Region, denormalised from the branch.',
  dpd_days              INT     COMMENT 'Days past due at month end. Zero means the account is current and not delinquent.',
  dpd_bucket            STRING  COMMENT 'Regulatory ageing bucket derived from dpd_days: "0-Current", "1-SMA0 (1-30)", "2-SMA1 (31-60)", "3-SMA2 (61-90)", "4-NPA (90+)". SMA means Special Mention Account. Use this for bucket-wise reporting.',
  outstanding_principal DOUBLE  COMMENT 'Outstanding principal in INR at that snapshot.',
  overdue_amount        DOUBLE  COMMENT 'Amount overdue in INR at that snapshot. Zero when the account is current.',
  is_npa                BOOLEAN COMMENT 'TRUE when dpd_days is greater than 90, i.e. the account is a Non-Performing Asset. GNPA percentage is NPA outstanding divided by total outstanding.',
  roll_direction        STRING  COMMENT 'Bucket movement versus the account\'s previous month: "forward" means it deteriorated into a worse bucket, "backward" means it improved, "stable" means unchanged (or the first month on record). Roll-forward rate is the share of accounts with roll_direction = forward.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Month-end delinquency snapshot, one row per loan account per month from 2025-03. THE PRIMARY TABLE for delinquency, DPD, bucket, NPA and roll-rate questions. Grain is snapshot_month x loan_account_id, so always aggregate rather than returning raw rows.'
AS SELECT snapshot_month, loan_account_id, product_code, branch_id, region, dpd_days, dpd_bucket,
          outstanding_principal, overdue_amount, is_npa, roll_direction
FROM core_delinquency;

CREATE OR REFRESH MATERIALIZED VIEW collections_activity (
  activity_id           STRING    COMMENT 'Activity identifier, primary key.',
  activity_date         DATE      COMMENT 'Date of the contact attempt (IST).',
  contact_ts_ist        TIMESTAMP COMMENT 'Date and time of the contact attempt in Indian Standard Time.',
  contact_hour          INT       COMMENT 'Hour of day of contact in IST, 24-hour clock, e.g. 20 means 8pm. RBI permits borrower contact only between 08:00 and 19:00.',
  loan_account_id       STRING    COMMENT 'Loan account contacted. Join to loan_accounts.',
  product_code          STRING    COMMENT 'Product code, denormalised.',
  branch_id             STRING    COMMENT 'Branch code, denormalised.',
  region                STRING    COMMENT 'Region, denormalised.',
  agent_id              STRING    COMMENT 'Recovery agent who made contact. Join to recovery_agents to check RBI conduct certification.',
  channel               STRING    COMMENT 'Contact channel: Tele-calling, SMS, Field Visit, WhatsApp, Email, or Legal Notice.',
  outcome               STRING    COMMENT 'Result of contact. "Contacted - PTP" means the borrower gave a promise to pay. Other values: Contacted - Refused, Contacted - Disputed, Not Reachable, Wrong Number, Paid, Partial Payment.',
  promise_to_pay_amount DOUBLE    COMMENT 'Amount in INR the borrower promised to pay. Zero when no promise was given.',
  amount_collected      DOUBLE    COMMENT 'Amount in INR actually collected during this contact. Zero when nothing was collected.',
  within_rbi_hours      BOOLEAN   COMMENT 'TRUE when the contact falls inside the RBI-permitted 08:00 to 19:00 IST window. FALSE indicates a potential conduct breach that must be investigated and reported.',
  source_system         STRING    COMMENT 'Which system reported the contact: dialer (calls and messages) or field_app (field visits).'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Collections contact attempts by field and tele-calling agents, conformed from the dialer vendor and the field-collection app. One row per attempt, de-duplicated. Includes contact_hour and within_rbi_hours so RBI recovery-agent conduct rules can be audited.'
AS SELECT * FROM core_collections_activity;

CREATE OR REFRESH MATERIALIZED VIEW recovery_agents (
  agent_id               STRING  COMMENT 'Recovery agent identifier, primary key. Format AGnnn.',
  agent_name             STRING  MASK ${catalog}.${schema}.mask_person_name COMMENT 'Agent full name; initials only for callers not cleared to see names.',
  agency_name            STRING  COMMENT 'Collection agency employing the agent. Banks remain accountable for agency conduct under RBI rules.',
  branch_id              STRING  COMMENT 'Branch the agent is mapped to.',
  region                 STRING  COMMENT 'Region the agent operates in.',
  rbi_conduct_certified  BOOLEAN COMMENT 'TRUE when the agent has completed mandatory RBI recovery-agent conduct training. An uncertified agent MUST NOT be assigned to a field visit.',
  certification_expiry   DATE    COMMENT 'Date the conduct certification expires. A certification expiring before the visit date is treated as uncertified.',
  active_flag            BOOLEAN COMMENT 'TRUE when the agent is currently active.',
  complaints_against_ytd INT     COMMENT 'Number of borrower complaints raised against this agent year to date. Agents with 3 or more complaints warrant review.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Field recovery agents employed through collection agencies. Carries the RBI conduct-certification status that governs whether an agent may be assigned to a borrower visit.'
AS SELECT * FROM core_recovery_agents;

CREATE OR REFRESH MATERIALIZED VIEW repayment_schedule (
  loan_account_id     STRING COMMENT 'Loan account number, primary key. Join to loan_accounts.',
  product_code        STRING COMMENT 'Product code, denormalised.',
  branch_id           STRING COMMENT 'Branch code, denormalised.',
  region              STRING COMMENT 'Region, denormalised.',
  next_due_date       DATE   COMMENT 'Date the next instalment falls due. Use for "due this week" or upcoming-collection questions.',
  emi_amount          DOUBLE COMMENT 'Monthly instalment amount in INR.',
  emis_paid           INT    COMMENT 'Count of instalments paid so far.',
  emis_pending        INT    COMMENT 'Count of instalments still outstanding.',
  last_payment_date   DATE   COMMENT 'Date of the most recent payment received.',
  last_payment_amount DOUBLE COMMENT 'Amount in INR of the most recent payment.',
  mandate_type        STRING COMMENT 'Repayment mandate: NACH (auto-debit), Cheque, Cash, or UPI Autopay. NACH failures are a leading delinquency indicator.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Per-loan repayment position: next due date, instalments paid and pending, last payment, and mandate type. One row per amortising loan account.'
AS SELECT * FROM core_repayment_schedule;

-- ============================================================ service and grievance
CREATE OR REFRESH MATERIALIZED VIEW complaint_categories (
  category_code STRING COMMENT 'Category code, primary key. UPI=UPI dispute, PAY=payment failure, CRD=card dispute, LON=loan servicing, DEP=deposit servicing, MIS=mis-selling, REC=recovery agent conduct, ATM=ATM/cash, KYC=KYC documentation, CHG=unauthorised charges.',
  category_name STRING COMMENT 'Description of the complaint category.',
  rbi_category  STRING COMMENT 'RBI Integrated Ombudsman Scheme ground of complaint, e.g. "Payment systems", "Recovery agents", "Mis-selling", "Levy of charges". Use this for regulatory reporting roll-ups.',
  sla_days      INT    COMMENT 'Turnaround SLA in calendar days for this category. A complaint resolved after this many days is an SLA breach.'
)
COMMENT 'Complaint category dimension mapping internal categories to RBI Integrated Ombudsman Scheme grounds, with the turnaround SLA in days for each.'
AS SELECT * FROM core_complaint_categories;

CREATE OR REFRESH MATERIALIZED VIEW complaints (
  complaint_id           STRING  COMMENT 'Complaint reference, primary key. Format CMnnnnnnn.',
  received_date          DATE    COMMENT 'Date the complaint was received. Filter on this for volume-over-time questions.',
  channel                STRING  COMMENT 'Intake channel: Branch, Call Centre, Email, Mobile App, Website, RBI CMS, or Social Media. RBI CMS means the complaint arrived through the RBI Complaint Management System, which is a regulatory escalation.',
  category_code          STRING  COMMENT 'Complaint category. Join to complaint_categories for the name.',
  rbi_category           STRING  COMMENT 'RBI Ombudsman ground of complaint, denormalised from complaint_categories.',
  customer_id            STRING  MASK ${catalog}.${schema}.mask_customer_id COMMENT 'Complaining customer, or a CU- pseudonym for callers not cleared to see identifiers. Join to customer_portfolio.',
  branch_id              STRING  COMMENT 'Branch the complaint is attributed to.',
  region                 STRING  COMMENT 'Region of the branch, denormalised.',
  product_code           STRING  COMMENT 'Product the complaint relates to.',
  severity               STRING  COMMENT 'Assessed severity: Low, Medium, High, or Critical.',
  status                 STRING  COMMENT 'Current state: Open, Resolved, or "Closed - No Deficiency". Open complaints have a NULL resolved_date.',
  resolved_date          DATE    COMMENT 'Date the complaint was resolved. NULL while the complaint is still open.',
  days_to_resolve        INT     COMMENT 'Calendar days taken to resolve. NULL while still open.',
  sla_days               INT     COMMENT 'The SLA in days that applied to this complaint, denormalised from complaint_categories.',
  sla_breached           BOOLEAN COMMENT 'TRUE when the complaint took longer than sla_days to resolve, or is still open beyond its SLA as at 2026-08-31. This is the headline regulatory metric.',
  escalated_to_ombudsman BOOLEAN COMMENT 'TRUE when the complaint was escalated to the RBI Ombudsman. Escalations are the most serious outcome.',
  repeat_complainant     BOOLEAN COMMENT 'TRUE when this customer has complained before. Repeat complainants indicate unresolved root causes.',
  complaint_text         STRING  MASK ${catalog}.${schema}.mask_complaint_text COMMENT 'Free-text description of the complaint as recorded by the agent. Redacted for callers not cleared to read free text.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Customer complaints across all channels from 2025-03. THE PRIMARY TABLE for grievance, SLA, and ombudsman questions.'
AS SELECT * FROM core_complaints;

CREATE OR REFRESH MATERIALIZED VIEW upi_disputes (
  dispute_id         STRING  COMMENT 'Dispute identifier, primary key.',
  txn_date           DATE    COMMENT 'Date of the disputed UPI transaction.',
  raised_date        DATE    COMMENT 'Date the dispute was raised by the customer.',
  customer_id        STRING  MASK ${catalog}.${schema}.mask_customer_id COMMENT 'Customer who raised the dispute, or a CU- pseudonym.',
  branch_id          STRING  COMMENT 'Branch the customer belongs to.',
  txn_amount         DOUBLE  COMMENT 'Disputed transaction amount in INR.',
  failure_reason     STRING  COMMENT 'Why the transaction failed: "Timeout at beneficiary bank", "Beneficiary bank declined", "Insufficient balance", "Invalid VPA", "Switch degradation", "Debit success credit pending", or "Duplicate submission".',
  resolution_path    STRING  COMMENT 'How the dispute was handled: Auto-refund, Manual investigation, Chargeback raised, or Merchant recovery.',
  auto_refunded      BOOLEAN COMMENT 'TRUE when the dispute was resolved automatically without manual intervention. The auto-refund rate is the key operational efficiency metric here.',
  resolution_seconds INT     COMMENT 'Seconds taken to resolve. Auto-refunds resolve within 30 seconds; manual investigation takes hours to days.',
  status             STRING  COMMENT 'Open or Closed.',
  psp_handle         STRING  COMMENT 'UPI payment service provider handle used (synthetic handles).',
  region             STRING  COMMENT 'Region of the branch, denormalised.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'UPI transaction disputes and their resolution path. Auto-refund reflects the NPCI rule that timed-out or declined UPI transactions are reversed automatically.'
AS SELECT * FROM core_upi_disputes;

CREATE OR REFRESH MATERIALIZED VIEW chargebacks (
  chargeback_id     STRING COMMENT 'Chargeback case identifier, primary key.',
  txn_date          DATE   COMMENT 'Date of the disputed card transaction.',
  raised_date       DATE   COMMENT 'Date the chargeback was raised.',
  customer_id       STRING MASK ${catalog}.${schema}.mask_customer_id COMMENT 'Cardholder, or a CU- pseudonym.',
  card_type         STRING COMMENT 'Credit, Debit, or Prepaid.',
  merchant_category STRING COMMENT 'Merchant category, e.g. Airlines, E-commerce, Fuel, Gaming, Subscription.',
  txn_amount        DOUBLE COMMENT 'Disputed amount in INR.',
  reason_code       STRING COMMENT 'Network reason code description, e.g. "Fraud - card not present", "Goods not received", "Duplicate processing".',
  liability         STRING COMMENT 'Which party bears the loss: Bank or Merchant.',
  status            STRING COMMENT 'Case outcome: Won, Lost, Open, or Withdrawn. Win rate is Won divided by the count of resolved cases (Won plus Lost).',
  days_open         INT    COMMENT 'Days the case has been or was open.',
  recovered_amount  DOUBLE COMMENT 'Amount in INR recovered. Zero unless the case was won.'
)
COMMENT 'Card chargeback cases with reason code, liability assignment and outcome. Use for card dispute win-rate and fraud-loss questions.'
AS SELECT * FROM core_chargebacks;

-- A genuine rollup of complaints, not an independent table. It used to be generated with its own random
-- numbers and claimed 56,009 complaints against an actual 9,660; a pre-aggregate that disagrees with its
-- own detail table is the fastest way to lose an analytics team's trust. Cells with no complaints are
-- absent rather than invented, so every number here reconciles to complaints.
CREATE OR REFRESH MATERIALIZED VIEW sla_tracker (
  report_month          DATE   COMMENT 'Reporting month, first day of month.',
  branch_id             STRING COMMENT 'Branch code.',
  region                STRING COMMENT 'Region, denormalised for regional roll-ups without a join.',
  rbi_category          STRING COMMENT 'RBI Ombudsman ground of complaint.',
  complaints_received   BIGINT COMMENT 'Complaints received in the month for this branch and category.',
  complaints_resolved   BIGINT COMMENT 'Of those, complaints resolved by the reporting date.',
  within_sla            BIGINT COMMENT 'Complaints received in the month that did not breach their SLA.',
  breached_sla          BIGINT COMMENT 'Complaints received in the month that breached their SLA, open or closed. SLA breach rate is breached_sla divided by complaints_received.',
  avg_days_to_resolve   DOUBLE COMMENT 'Average calendar days to resolve, over the resolved complaints.',
  ombudsman_escalations BIGINT COMMENT 'Count escalated to the RBI Ombudsman.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Monthly complaint SLA performance by branch and RBI category, aggregated from complaints by the pipeline. PREFER THIS TABLE over raw complaints for trend and SLA-breach-rate questions: it is small and cannot be silently truncated.'
AS SELECT trunc(received_date, 'MM') AS report_month, branch_id, region, rbi_category,
          count(*) AS complaints_received,
          count_if(status <> 'Open') AS complaints_resolved,
          count_if(NOT sla_breached) AS within_sla,
          count_if(sla_breached) AS breached_sla,
          round(avg(days_to_resolve), 1) AS avg_days_to_resolve,
          count_if(escalated_to_ombudsman) AS ombudsman_escalations
FROM core_complaints
GROUP BY ALL;

-- ============================================================ RM performance and incentives
CREATE OR REFRESH MATERIALIZED VIEW relationship_managers (
  rm_id           STRING  COMMENT 'Relationship manager identifier, primary key. Format RMnnnn.',
  rm_name         STRING  MASK ${catalog}.${schema}.mask_person_name COMMENT 'RM full name; initials only for callers not cleared to see names.',
  branch_id       STRING  COMMENT 'Branch the RM is posted at.',
  region          STRING  COMMENT 'Region.',
  zone            STRING  COMMENT 'Branch zone: Metro, Urban, Semi-Urban, Rural.',
  rm_grade        STRING  COMMENT 'Seniority grade: Junior, Mid, Senior, or Lead. Grade determines the incentive slab grid and target size.',
  date_joined     DATE    COMMENT 'Date the RM joined the bank.',
  portfolio_count INT     COMMENT 'Number of customers in the RM portfolio as recorded by HRMS.',
  active_flag     BOOLEAN COMMENT 'TRUE when the RM is currently employed and active.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Relationship manager dimension. One row per RM, 180 RMs. Join on rm_id.'
AS SELECT * FROM core_relationship_managers;

CREATE OR REFRESH MATERIALIZED VIEW incentive_slabs (
  slab_id               STRING  COMMENT 'Slab identifier, primary key.',
  rm_grade              STRING  COMMENT 'RM grade the slab applies to.',
  attainment_from_pct   DOUBLE  COMMENT 'Lower bound of the attainment band, inclusive, as a percentage.',
  attainment_to_pct     DOUBLE  COMMENT 'Upper bound of the attainment band, exclusive, as a percentage.',
  payout_pct_of_target  DOUBLE  COMMENT 'Payout multiple applied to the target incentive for this band. 1.00 means a full payout, 1.60 means 160 percent.',
  quality_gate_required BOOLEAN COMMENT 'TRUE when this band requires the product-mix quality gate to be cleared. Applies at full payout and above.',
  min_product_mix_score DOUBLE  COMMENT 'Minimum product_mix_score needed to clear the quality gate for this band. Zero when no gate applies.'
)
COMMENT 'Incentive slab grid by RM grade. Defines the payout multiple for each attainment band and the product-mix quality gate that must be cleared before a full payout is released.'
AS SELECT * FROM core_incentive_slabs;

CREATE OR REFRESH MATERIALIZED VIEW rm_targets (
  target_month             DATE   COMMENT 'Target month, first day of month.',
  rm_id                    STRING COMMENT 'Relationship manager identifier.',
  branch_id                STRING COMMENT 'Branch code.',
  region                   STRING COMMENT 'Region.',
  rm_grade                 STRING COMMENT 'RM grade.',
  target_casa_amount       DOUBLE COMMENT 'CASA target in INR. CASA means Current Account and Savings Account balances.',
  target_loan_amount       DOUBLE COMMENT 'Loan disbursal target in INR.',
  target_cards             INT    COMMENT 'Target count of new credit cards sourced.',
  target_insurance         INT    COMMENT 'Target count of insurance policies sold.',
  target_product_mix_score DOUBLE COMMENT 'Target product-mix score, 0 to 1. Measures balance across product lines rather than volume in one.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Monthly RM targets by product line. Grain is target_month x rm_id. Join to rm_achievement on the same grain to compute attainment.'
AS SELECT * FROM core_rm_targets;

CREATE OR REFRESH MATERIALIZED VIEW rm_achievement (
  achievement_month   DATE    COMMENT 'Achievement month, first day of month.',
  rm_id               STRING  COMMENT 'Relationship manager identifier. Join to relationship_managers.',
  branch_id           STRING  COMMENT 'Branch code.',
  region              STRING  COMMENT 'Region.',
  rm_grade            STRING  COMMENT 'RM grade.',
  actual_casa_amount  DOUBLE  COMMENT 'CASA balances actually sourced in INR.',
  actual_loan_amount  DOUBLE  COMMENT 'Loans actually disbursed in INR.',
  actual_cards        INT     COMMENT 'Credit cards actually sourced.',
  actual_insurance    INT     COMMENT 'Insurance policies actually sold. A low value alongside high CASA and loan volume is the signature of a distorted product mix.',
  product_mix_score   DOUBLE  COMMENT 'Product-mix quality score, 0 to 1. Below 0.50 indicates volume concentrated in one or two products. This is the quality gate input.',
  attainment_pct      DOUBLE  COMMENT 'Overall attainment as a percentage, the average of CASA attainment and loan attainment. 100 means target met exactly. Derived by the pipeline.',
  incentive_earned    DOUBLE  COMMENT 'Incentive earned in INR for the month, after applying the slab payout multiple and the quality gate. Derived by the pipeline.',
  quality_gate_passed BOOLEAN COMMENT 'TRUE when product_mix_score cleared the minimum required by the attainment slab. FALSE means the payout was halved.',
  clawback_flag       BOOLEAN COMMENT 'TRUE when the RM attained a full-payout band but failed the quality gate, so part of the incentive is subject to clawback. Use this to find incentive distortion.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Monthly RM achievement, attainment and incentive earned. THE PRIMARY TABLE for RM performance and incentive questions. Attainment, incentive, quality gate and clawback are computed by the pipeline from the sales system actuals, the targets and the slab grid.'
AS SELECT * FROM core_rm_achievement;

CREATE OR REFRESH MATERIALIZED VIEW customer_portfolio (
  customer_id              STRING  MASK ${catalog}.${schema}.mask_customer_id COMMENT 'Customer identifier, primary key. Format CUnnnnnn, or a CU- pseudonym.',
  rm_id                    STRING  COMMENT 'Relationship manager who owns this customer.',
  branch_id                STRING  COMMENT 'Home branch.',
  region                   STRING  COMMENT 'Region.',
  customer_segment         STRING  COMMENT 'Wealth segment: Mass, Mass Affluent, Affluent, Private, or MSME.',
  relationship_start       DATE    COMMENT 'Date the customer relationship began.',
  total_relationship_value DOUBLE  COMMENT 'Total relationship value in INR across all products.',
  products_held            INT     COMMENT 'Count of distinct products the customer holds. Low counts are cross-sell opportunities.',
  casa_balance             DOUBLE  COMMENT 'Current and savings account balance in INR.',
  risk_rating              STRING  COMMENT 'Internal credit risk rating: Low, Medium, or High.',
  nri_flag                 BOOLEAN COMMENT 'TRUE when the customer is a Non-Resident Indian.',
  churn_risk_score         DOUBLE  COMMENT 'Modelled churn probability, 0 to 1. Above 0.7 warrants retention action.'
)
WITH ROW FILTER ${catalog}.${schema}.region_visible ON (region)
COMMENT 'Customer master with the owning relationship manager, segment, relationship value and churn risk. Join on customer_id to reach complaints or loans, and on rm_id to reach RM performance.'
AS SELECT * FROM core_customer_portfolio;

CREATE OR REFRESH MATERIALIZED VIEW product_holdings (
  holding_id          STRING  COMMENT 'Holding identifier, primary key.',
  customer_id         STRING  MASK ${catalog}.${schema}.mask_customer_id COMMENT 'Customer identifier, or a CU- pseudonym.',
  rm_id               STRING  COMMENT 'Relationship manager who owns the customer.',
  product_code        STRING  COMMENT 'Product held. Join to product_master.',
  opened_date         DATE    COMMENT 'Date the product was opened.',
  balance_or_limit    DOUBLE  COMMENT 'Balance for deposits or credit limit for lending products, in INR.',
  is_active           BOOLEAN COMMENT 'TRUE when the holding is currently active.',
  cross_sell_eligible BOOLEAN COMMENT 'TRUE when the customer is eligible for cross-sell on this relationship.'
)
COMMENT 'One row per product a customer holds. Use for cross-sell gap analysis: compare products held against the full product_master list for a segment.'
AS SELECT * FROM core_product_holdings;

-- ============================================================ documents
CREATE OR REFRESH MATERIALIZED VIEW complaint_documents (
  doc_id          STRING    COMMENT 'Document identifier: its path in the landing volume.',
  complaint_id    STRING    COMMENT 'Complaint the letter belongs to. Join to complaints. NULL for reference documents.',
  document_type   STRING    COMMENT 'customer_letter, compliance_note or agency_agreement.',
  file_name       STRING    COMMENT 'File name as received.',
  region          STRING    COMMENT 'Region of the complaint\'s branch. NULL for the bank\'s reference documents, which every reader may see.',
  file_size_bytes BIGINT    COMMENT 'File size in bytes.',
  ingested_at     TIMESTAMP COMMENT 'When the pipeline ingested the file.',
  document_text   STRING    MASK ${catalog}.${schema}.mask_complaint_text COMMENT 'Full text. Customer letters are redacted for callers not cleared to read free text.'
)
-- Letters belong to a complaint, so they inherit its region; reference documents have no region and are
-- visible to everyone. The letter text is the same personal free text complaint_text is, so it carries
-- the same mask. Until this table was governed, the redaction on complaints.complaint_text could be
-- walked around by reading the scanned letter instead.
WITH ROW FILTER ${catalog}.${schema}.document_visible ON (region)
COMMENT 'Customer complaint letters and the bank\'s reference documents, with full text. Governed like complaints: letters follow the complaint\'s region and their text is masked for callers not cleared to read it.'
AS
SELECT l._source_path AS doc_id, regexp_extract(l._file_name, '^(CM[0-9]+)', 1) AS complaint_id,
       'customer_letter' AS document_type, l._file_name AS file_name, c.region,
       l._file_size_bytes AS file_size_bytes, l._ingested_at AS ingested_at, l.letter_text AS document_text
FROM bronze_correspondence l
LEFT JOIN core_complaints c ON c.complaint_id = regexp_extract(l._file_name, '^(CM[0-9]+)', 1)
UNION ALL
SELECT _source_path, CAST(NULL AS STRING),
       CASE WHEN _source_path LIKE '%/agencies/%' THEN 'agency_agreement' ELSE 'compliance_note' END,
       _file_name, CAST(NULL AS STRING), _file_size_bytes, _ingested_at, document_text
FROM bronze_reference_docs;

-- ============================================================ the guardrail's independent count
-- The action guardrail checks that its own identity can see the WHOLE book, because a control that is
-- row-filtered out of the evidence reports "passed". It needs an expectation formed independently of
-- any row filter: these counts are computed from the private core tables, which no policy touches, so
-- they cannot agree with a filter that is blinding the guardrail. No customer data, counts only.
CREATE OR REFRESH MATERIALIZED VIEW gold_row_counts (
  table_name STRING COMMENT 'Governed gold table.',
  row_count  BIGINT COMMENT 'Rows in the table as computed by the pipeline, before any row filter.'
)
COMMENT 'Unfiltered row counts of the governed gold tables, computed by the pipeline from data no row filter applies to. The guardrail compares what its identity can see against these.'
AS
SELECT 'recovery_agents' AS table_name, count(*) AS row_count FROM core_recovery_agents UNION ALL
SELECT 'complaints', count(*) FROM core_complaints UNION ALL
SELECT 'delinquency_monthly', count(*) FROM core_delinquency UNION ALL
SELECT 'collections_activity', count(*) FROM core_collections_activity UNION ALL
SELECT 'loan_accounts', count(*) FROM core_loan_accounts UNION ALL
SELECT 'upi_disputes', count(*) FROM core_upi_disputes UNION ALL
SELECT 'chargebacks', count(*) FROM core_chargebacks UNION ALL
SELECT 'rm_achievement', count(*) FROM core_rm_achievement UNION ALL
SELECT 'rm_targets', count(*) FROM core_rm_targets UNION ALL
SELECT 'customer_portfolio', count(*) FROM core_customer_portfolio UNION ALL
SELECT 'product_holdings', count(*) FROM core_product_holdings UNION ALL
SELECT 'repayment_schedule', count(*) FROM core_repayment_schedule UNION ALL
SELECT 'relationship_managers', count(*) FROM core_relationship_managers UNION ALL
SELECT 'branch_master', count(*) FROM core_branch_master UNION ALL
SELECT 'product_master', count(*) FROM core_product_master UNION ALL
SELECT 'complaint_categories', count(*) FROM core_complaint_categories UNION ALL
SELECT 'incentive_slabs', count(*) FROM core_incentive_slabs;
