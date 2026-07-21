/**
 * src/api/outlook.ts
 * ===================
 * API calls for Outlook connector context endpoints.
 *
 * Endpoints
 * ---------
 * GET /api/v1/connectors/outlook/context?user_id=<id>
 *   Production endpoint — requires a real Microsoft OAuth token stored by
 *   AuthService.  Returns a ConnectorResult populated by OutlookConnector.
 *
 * GET /api/v1/connectors/demo/context?user_id=<id>
 *   Demo endpoint — no OAuth token required.  Only mounted by the backend
 *   when CONNECTOR_MODE=demo.  Returns a ConnectorResult populated by
 *   DemoOutlookConnector with the same shape as the production endpoint.
 *
 * Both endpoints return:
 *   status       — "success" | "partial" | "failed"
 *   collected_at — UTC ISO 8601 timestamp
 *   data         — { user: null, calendar_events: [...], emails: [...] }
 *   errors       — list of human-readable error strings
 */

import apiClient from './client.ts'
import type { ConnectorResult, OutlookData } from '../types/index.ts'

/**
 * Fetch the current Outlook context for a real OAuth user.
 *
 * Calls GET /api/v1/connectors/outlook/context — requires a valid
 * Microsoft OAuth token to be stored by the backend AuthService.
 * Throws AxiosError on network failure or non-2xx responses.
 */
export async function fetchOutlookContext(userId: string): Promise<ConnectorResult<OutlookData>> {
  const response = await apiClient.get<ConnectorResult<OutlookData>>(
    '/api/v1/connectors/outlook/context',
    { params: { user_id: userId } },
  )
  return response.data
}

/**
 * Fetch the demo Outlook context — no OAuth token required.
 *
 * Calls GET /api/v1/connectors/demo/context — only available when the
 * backend is running with CONNECTOR_MODE=demo.  Populated by
 * DemoOutlookConnector: the same connector that drives the recommendations
 * pipeline, ensuring displayed meetings and emails always match what Bob
 * reasoned over.
 *
 * Returns an identical ConnectorResult shape to fetchOutlookContext so
 * DashboardScreen, MeetingList, and EmailList require no changes.
 * Throws AxiosError on network failure or non-2xx responses.
 */
export async function fetchDemoContext(userId: string): Promise<ConnectorResult<OutlookData>> {
  const response = await apiClient.get<ConnectorResult<OutlookData>>(
    '/api/v1/connectors/demo/context',
    { params: { user_id: userId } },
  )
  return response.data
}
