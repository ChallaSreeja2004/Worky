/**
 * src/hooks/useRecommendations.ts
 * =================================
 * React hook for fetching and managing IBM Bob recommendations.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Call getRecommendations(userId) on mount and on manual refresh.
 *   • Expose typed RecommendationSet data to the component tree.
 *   • Manage loading, error, and stale-data states.
 *   • Never replace visible recommendations with empty state during refresh.
 *   • Cancel in-flight requests on unmount or when userId changes.
 *
 * RULES
 * -----
 *   • Only ScreenManager calls this hook — it passes the result as props
 *     into DashboardScreen.  No component further down the tree fetches data.
 *   • This hook never imports from any component file.
 *   • The refresh function is stable (useCallback) so it can be passed as
 *     a prop without triggering unnecessary re-renders.
 *
 * TIMING NOTE
 * -----------
 * Recommendations are generated on-demand by the backend — each call triggers
 * IBM Bob to reason over the current Outlook context.  The backend may take
 * 15–30 s on the first call.  The timeout on the API client (15 s) is
 * deliberately lower than Bob's worst-case latency, so the hook surfaces a
 * clear timeout error rather than hanging indefinitely.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getRecommendations } from '../services/recommendationsService.ts'
import type { RecommendationSet } from '../types/index.ts'

export interface RecommendationsState {
  /** The last successfully fetched RecommendationSet. Null before first fetch. */
  data: RecommendationSet | null
  /** True only during the very first fetch (no data shown yet). */
  isLoading: boolean
  /** True while a refresh is in flight and stale data is already shown. */
  isRefreshing: boolean
  /** Network or unexpected error message. Null when no error. */
  error: string | null
  /** Call to manually re-fetch recommendations. */
  refresh: () => void
}

export function useRecommendations(userId: string | undefined): RecommendationsState {
  // Initialise isLoading to true when userId is defined so the spinner is shown
  // immediately — before the first async tick — preventing an empty-state flash.
  const [data,         setData]         = useState<RecommendationSet | null>(null)
  const [isLoading,    setIsLoading]    = useState(() => Boolean(userId))
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error,        setError]        = useState<string | null>(null)

  // Hold an AbortController ref so the active fetch can be cancelled on cleanup.
  const abortRef = useRef<AbortController | null>(null)

  const doFetch = useCallback(async (initial: boolean) => {
    if (!userId) return

    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    if (initial) {
      setIsLoading(true)
    } else {
      setIsRefreshing(true)
    }
    setError(null)

    try {
      const result = await getRecommendations(userId)
      if (controller.signal.aborted) return
      setData(result)
    } catch (err: unknown) {
      if (controller.signal.aborted) return
      const message =
        err instanceof Error ? err.message : 'Could not reach the Worky backend.'
      setError(message)
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false)
        setIsRefreshing(false)
      }
    }
  }, [userId])

  useEffect(() => {
    if (userId) {
      void doFetch(true)
    } else {
      setIsLoading(false)
    }
    return () => {
      abortRef.current?.abort()
    }
  }, [userId, doFetch])

  const refresh = useCallback(() => {
    void doFetch(false)
  }, [doFetch])

  return { data, isLoading, isRefreshing, error, refresh }
}
