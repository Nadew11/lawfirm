import { supabase } from './supabaseClient'

/**
 * Fire-and-forget audit log entry for application-layer events
 * (primarily SELECT / read operations that can't be captured by
 * database triggers).
 *
 * firm_id is auto-set by the RLS INSERT policy (must match the
 * authenticated user's firm). user_id defaults to auth.uid() via
 * the trigger/policy context.
 *
 * @param {'SELECT'|'INSERT'|'UPDATE'|'DELETE'} action
 * @param {string} tableName
 * @param {string|null} recordId  UUID of the record, or null for bulk reads
 * @param {object} metadata      Optional context (e.g. { count: 16 })
 */
export function logAudit(action, tableName, recordId = null, metadata = {}) {
  supabase
    .from('audit_log')
    .insert({
      action,
      table_name: tableName,
      record_id: recordId,
      metadata,
    })
    .then()
}
