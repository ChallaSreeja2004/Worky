/**
 * src/api/outlook.ts
 * ===================
 * API call for the Outlook connector context endpoint.
 *
 * This is the only module in the codebase that calls the Outlook context
 * endpoint.  It wraps the raw Axios response in a typed ConnectorResult.
 *
 * Endpoint
 * --------
 * GET /api/v1/connectors/outlook/context?user_id=<id>
 *
 * Returns ConnectorResult with:
 *   status       — "success" | "partial" | "failed"
 *   collected_at — UTC ISO 8601 timestamp
 *   data         — { user: null, calendar_events: [], emails: [] }
 *   errors       — list of human-readable error strings
 */

import apiClient from './client.ts'
import type { ConnectorResult, OutlookData } from '../types/index.ts'

/**
 * Fetch the current Outlook context for the given user.
 *
 * Throws AxiosError on network failure or non-2xx responses.
 * The hook layer (useOutlookContext) is responsible for catching errors.
 */
export async function fetchOutlookContext(userId: string): Promise<ConnectorResult<OutlookData>> {
  const response = await apiClient.get<ConnectorResult<OutlookData>>(
    '/api/v1/connectors/outlook/context',
    { params: { user_id: userId } },
  )
  return response.data
}
