/**
 * src/services/outlookService.ts
 * ================================
 * Domain-level wrappers around the Outlook connector context API calls.
 *
 * Services sit between the API layer and the hook layer.  They contain
 * domain logic that is too specific for the API layer but not reactive
 * enough for a hook.  This service is currently thin — it re-exports the
 * API calls with domain-facing names.  As Phase 6 adds caching or
 * pre-processing, the logic grows here without touching the hook.
 *
 * Rules
 * -----
 *   • No React imports.  Services are plain TypeScript.
 *   • No direct axios calls.  All HTTP goes through src/api/.
 *   • No localStorage or sessionStorage.
 */

import { fetchDemoContext, fetchOutlookContext } from '../api/outlook.ts'
import type { ConnectorResult, OutlookData } from '../types/index.ts'

/**
 * Retrieve the current Outlook context for a real OAuth user.
 *
 * Calls GET /api/v1/connectors/outlook/context — requires a valid
 * Microsoft OAuth token.  Used by useOutlookContext in Outlook Mode.
 */
export async function getOutlookContext(userId: string): Promise<ConnectorResult<OutlookData>> {
  return fetchOutlookContext(userId)
}

/**
 * Retrieve the synthetic Outlook context for a demo session.
 *
 * Calls GET /api/v1/connectors/demo/context — no OAuth token required.
 * Only available when the backend is running with CONNECTOR_MODE=demo.
 * Used by useOutlookContext in Demo Mode.
 */
export async function getDemoContext(userId: string): Promise<ConnectorResult<OutlookData>> {
  return fetchDemoContext(userId)
}
