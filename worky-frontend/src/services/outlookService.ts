/**
 * src/services/outlookService.ts
 * ================================
 * Domain-level wrapper around the Outlook API call.
 *
 * Services sit between the API layer and the hook layer.  They contain
 * domain logic that is too specific for the API layer but not reactive
 * enough for a hook.  This service is currently thin — it re-exports the
 * API call with a domain-facing name.  As Phase 6 adds caching or
 * pre-processing, the logic grows here without touching the hook.
 *
 * Rules
 * -----
 *   • No React imports.  Services are plain TypeScript.
 *   • No direct axios calls.  All HTTP goes through src/api/.
 *   • No localStorage or sessionStorage.
 */

import { fetchOutlookContext } from '../api/outlook.ts'
import type { ConnectorResult, OutlookData } from '../types/index.ts'

/**
 * Retrieve the current Outlook context for the authenticated user.
 *
 * This is the single call site used by useOutlookContext.  Keeping it here
 * isolates the hook from knowing which API module or endpoint to call.
 */
export async function getOutlookContext(userId: string): Promise<ConnectorResult<OutlookData>> {
  return fetchOutlookContext(userId)
}
