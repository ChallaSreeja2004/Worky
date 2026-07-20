/**
 * src/services/recommendationsService.ts
 * ========================================
 * Domain-level wrapper around the recommendations API call.
 *
 * Services sit between the API layer and the hook layer.  This service is
 * intentionally thin — it re-exports the API call with a domain-facing name.
 * Any pre-processing or caching logic added in the future belongs here without
 * touching the hook.
 *
 * Rules
 * -----
 *   • No React imports.  Services are plain TypeScript.
 *   • No direct axios calls.  All HTTP goes through src/api/.
 *   • No localStorage or sessionStorage.
 */

import { fetchRecommendations } from '../api/recommendations.ts'
import type { RecommendationSet } from '../types/index.ts'

/**
 * Retrieve the current IBM Bob recommendation set for the authenticated user.
 *
 * This is the single call site used by useRecommendations.  Keeping it here
 * isolates the hook from knowing which API module or endpoint to call.
 */
export async function getRecommendations(userId: string): Promise<RecommendationSet> {
  return fetchRecommendations(userId)
}
