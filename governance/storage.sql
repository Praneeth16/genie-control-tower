-- Schema and volumes. Created by the setup job rather than declared as bundle resources: in development
-- mode a bundle prefixes UC schema names per user, and every SQL file, Genie space and policy function in
-- this project names the schema literally. Placeholders: ${CATALOG}, ${SCHEMA}.
CREATE SCHEMA IF NOT EXISTS ${CATALOG}.${SCHEMA}
  COMMENT 'Genie Control Tower: a synthetic retail bank\'s collections, grievance and RM book, from raw source files to governed gold tables. All data is synthetic.';
CREATE VOLUME IF NOT EXISTS ${CATALOG}.${SCHEMA}.landing
  COMMENT 'Where source systems drop their files. Auto Loader reads from here; nothing writes back.';
CREATE VOLUME IF NOT EXISTS ${CATALOG}.${SCHEMA}.holdback
  COMMENT 'The most recent period, held back so a demo can land it live and watch the file-arrival trigger run the cycle.';
CREATE VOLUME IF NOT EXISTS ${CATALOG}.${SCHEMA}.docs
  COMMENT 'Drafted customer correspondence written by the app.';
