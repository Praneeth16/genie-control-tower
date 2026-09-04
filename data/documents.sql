-- The volumes lane: make the unstructured corpus queryable alongside the structured tables.
--
-- Why this table exists rather than a separate document search tool: a grievance officer's question is
-- "what did this customer actually say, and does it match what our systems recorded?" Answering that
-- needs the letter and the complaint row in the SAME query. Keeping the parsed text as a Delta table
-- in the same schema means Genie can join it to `complaints` with no extra machinery, and the row
-- filters and column masks that protect the structured data protect this too.
--
-- `wholetext => true` is the important option: without it read_files returns one row per LINE, which
-- would shred each letter into fragments and make any join on complaint_id meaningless.

CREATE OR REPLACE TABLE complaint_documents
COMMENT 'Text of inbound customer complaint letters, internal compliance notes and recovery agency service agreements, parsed from the docs volume. One row per document. Joins to complaints on complaint_id for letters. All content is synthetic.'
AS
SELECT
  -- The complaint id is the filename for a customer letter (CM0007800.txt) and NULL for the policy
  -- and contract documents, which belong to no single complaint.
  CASE WHEN regexp_extract(_metadata.file_name, '^(CM[0-9]+)\\.txt$', 1) != ''
       THEN regexp_extract(_metadata.file_name, '^(CM[0-9]+)\\.txt$', 1) END      AS complaint_id,
  CASE
    WHEN _metadata.file_path LIKE '%/complaints/%' THEN 'customer_letter'
    WHEN _metadata.file_path LIKE '%/compliance/%' THEN 'compliance_note'
    WHEN _metadata.file_path LIKE '%/agencies/%'   THEN 'agency_agreement'
    ELSE 'other'
  END                                                                             AS document_type,
  _metadata.file_name                                                             AS file_name,
  _metadata.file_path                                                             AS file_path,
  _metadata.file_size                                                             AS file_size_bytes,
  CAST(_metadata.file_modification_time AS TIMESTAMP)                             AS ingested_at,
  value                                                                           AS document_text
FROM read_files(
  '/Volumes/${CATALOG}/${SCHEMA}//docs',
  format => 'text',
  wholetext => true,
  recursiveFileLookup => true
);

ALTER TABLE complaint_documents ALTER COLUMN complaint_id    COMMENT 'Complaint this document relates to, parsed from the file name. NULL for compliance notes and agency agreements, which are not specific to one complaint.';
ALTER TABLE complaint_documents ALTER COLUMN document_type   COMMENT 'customer_letter, compliance_note or agency_agreement. Filter on this before searching text: a phrase found in an agency contract means something entirely different from the same phrase in a customer letter.';
ALTER TABLE complaint_documents ALTER COLUMN file_name       COMMENT 'Source file name in the docs volume.';
ALTER TABLE complaint_documents ALTER COLUMN file_path       COMMENT 'Full Unity Catalog volume path, so a user can open the original document.';
ALTER TABLE complaint_documents ALTER COLUMN document_text   COMMENT 'Full text of the document. Free text that may describe a customer situation in their own words; treat as sensitive.';
ALTER TABLE complaint_documents ALTER COLUMN ingested_at     COMMENT 'When the file last changed in the volume.';

ALTER TABLE complaint_documents SET TAGS ('domain' = 'operations');
-- Free text written by a customer is the highest-risk column in the schema: it can contain anything
-- they chose to write, including identifiers no structured field would hold.
ALTER TABLE complaint_documents ALTER COLUMN document_text SET TAGS ('data_classification' = 'pii');
