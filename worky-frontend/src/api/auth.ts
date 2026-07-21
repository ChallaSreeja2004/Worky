/**
 * src/api/auth.ts
 * ================
 * API call for the demo authentication endpoint.
 *
 * Endpoint
 * --------
 * POST /api/v1/auth/demo
 *
 * Available only when the backend is running with CONNECTOR_MODE=demo.
 * Returns a synthetic WorkyUser that callers pass directly to
 * AuthContext.login().
 *
 * Using apiClient here (rather than a raw fetch) keeps the backend base URL
 * as a single source of truth in src/api/client.ts, exactly as every other
 * API call in the project does.
 */

import apiClient from './client.ts'
import type { WorkyUser } from '../types/index.ts'

/**
 * Call POST /api/v1/auth/demo and return the synthetic user identity.
 *
 * Throws AxiosError on network failure, non-2xx responses, or when the
 * endpoint is not mounted (i.e. backend not in demo mode).
 */
export async function postDemoAuth(): Promise<WorkyUser> {
  const response = await apiClient.post<WorkyUser>('/api/v1/auth/demo')
  return response.data
}
