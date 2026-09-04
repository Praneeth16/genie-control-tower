-- The administrator role.
--
-- Three endpoints were reachable by any signed-in user and should not have been:
--   * the kill switch      — an ordinary user could resume actions after an emergency stop
--   * the audit feed       — it returns other people's email addresses and source IPs
--   * the outbound listing — it enumerates complaint ids from every region
--
-- None of those are per-record business data, so a row filter is the wrong tool; they are
-- administrative surfaces and need an administrative role. Reusing approver_roles keeps one directory
-- rather than inventing a second permission system that can drift from it.

SET search_path TO ${LAKEBASE_SCHEMA};

INSERT INTO approver_roles (principal, role, granted_by) VALUES
    ('${ADMIN_PRINCIPAL}', 'Control Tower Administrator', 'workshop-setup')
ON CONFLICT (principal, role) DO NOTHING;
