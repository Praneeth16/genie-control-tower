-- History is append-only by construction, not by convention. "Nothing updates action_events" was true
-- of the code and false of the database: any identity with write access could rewrite the lineage an
-- auditor relies on. These triggers refuse UPDATE and DELETE for every role, including the owner.

SET search_path TO ${LAKEBASE_SCHEMA};

CREATE OR REPLACE FUNCTION refuse_history_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS case_history_append_only ON case_history;
CREATE TRIGGER case_history_append_only BEFORE UPDATE OR DELETE ON case_history
    FOR EACH ROW EXECUTE FUNCTION refuse_history_change();

DROP TRIGGER IF EXISTS action_events_append_only ON action_events;
CREATE TRIGGER action_events_append_only BEFORE UPDATE OR DELETE ON action_events
    FOR EACH ROW EXECUTE FUNCTION refuse_history_change();
