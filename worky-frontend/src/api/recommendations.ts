/**
 * src/api/recommendations.ts
 * ===========================
 * API call for the recommendations endpoint.
 *
 * This is the only module in the codebase that calls
 * GET /api/v1/recommendations.
 *
 * Endpoint
 * --------
 * GET /api/v1/recommendations/?user_id=<id>
 *
 * Returns a RecommendationSet produced by IBM Bob after reasoning over
 * the user's Outlook context (and future connectors).
 *
 * Raises HTTP 401 when the user has not authenticated or their token
 * has expired — the response interceptor in client.ts handles this by
 * dispatching a worky:401 event that clears auth state.
 */

import apiClient from './client.ts'
import type { RecommendationSet } from '../types/index.ts'

/**
 * Fetch the current recommendation set for the given user.
 *
 * Throws AxiosError on network failure or non-2xx responses.
 * The hook layer (useRecommendations) is responsible for catching errors.
 */
export async function fetchRecommendations(userId: string): Promise<RecommendationSet> {
  const response = await apiClient.get<RecommendationSet>(
    '/api/v1/recommendations/',
    { params: { user_id: userId } },
  )
  return response.data
}
