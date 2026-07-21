/**
 * src/hooks/useOutlookContext.ts
 * ================================
 * React hook for fetching and managing Outlook connector data.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Call the correct context endpoint on mount and on manual refresh.
 *   • Expose typed ConnectorResult data to the component tree.
 *   • Manage loading, error, and stale-data states.
 *   • Never replace visible data with empty state while a refresh is in flight.
 *   • Cancel in-flight requests on unmount or when userId changes (AbortController).
 *
 * DEMO MODE
 * ---------
 *   When isDemo is true the hook calls getDemoContext() instead of
 *   getOutlookContext().  getDemoContext() calls
 *   GET /api/v1/connectors/demo/context which is backed by DemoOutlookConnector
 *   — the same connector the recommendations pipeline uses, so the displayed
 *   meetings and emails always match what Bob reasoned over.
 *   The production /connectors/outlook/context endpoint is never called for
 *   demo users.
 *
 * RULES
 * -----
 *   • Only ScreenManager calls this hook — it passes the result as props
 *     into DashboardScreen.  No component further down the tree fetches data.
 *   • This hook never imports from any component file.
 *   • The refresh function is stable (useCallback) so it can be passed as
 *     a prop without triggering re-renders in WidgetShell.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { getDemoContext, getOutlookContext } from '../services/outlookService.ts'
import type { ConnectorResult, ConnectorStatus, OutlookData } from '../types/index.ts'

export interface OutlookContextState {
  /** The last successfully fetched ConnectorResult. Null before first fetch. */
  result: ConnectorResult<OutlookData> | null
  /** True only during the very first fetch (no data shown yet). */
  isLoading: boolean
  /** True while a refresh is in flight and stale data is already shown. */
  isRefreshing: boolean
  /** Derived connector status — null before first fetch. */
  status: ConnectorStatus | null
  /** Network or unexpected error message. Null when no error. */
  error: string | null
  /** Call to manually re-fetch Outlook data. */
  refresh: () => void
}

export function useOutlookContext(userId: string | undefined, isDemo: boolean = false): OutlookContextState {
  // Initialise isLoading to true whenever userId is defined so the spinner
  // is shown immediately — before the first async tick — preventing an
  // empty-state flash.  This applies in both Outlook and Demo modes because
  // both now fetch a context endpoint on mount.
  const [result,       setResult]       = useState<ConnectorResult<OutlookData> | null>(null)
  const [isLoading,    setIsLoading]    = useState(() => Boolean(userId))
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [error,        setError]        = useState<string | null>(null)

  // C1: hold an AbortController ref so the active fetch can be cancelled on
  // cleanup (unmount) or when a new fetch supersedes an in-flight one.
  const abortRef = useRef<AbortController | null>(null)

  const doFetch = useCallback(async (initial: boolean) => {
    if (!userId) return

    // Cancel any still-running request before starting a new one.
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    // First fetch: show spinner.  Subsequent fetches: keep stale data visible.
    if (initial) {
      setIsLoading(true)
    } else {
      setIsRefreshing(true)
    }
    setError(null)

    try {
      const data = isDemo
        ? await getDemoContext(userId)
        : await getOutlookContext(userId)

      // If this request was aborted (component unmounted or superseded), do
      // not apply its result to avoid stale state overwrites.
      if (controller.signal.aborted) return

      setResult(data)
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
  }, [userId, isDemo])

  // Fetch on mount (or when userId becomes available after sign-in).
  useEffect(() => {
    if (userId) {
      void doFetch(true)
    } else {
      // userId cleared (logout) — reset loading state so it re-initialises
      // correctly on the next sign-in.
      setIsLoading(false)
    }

    // Cleanup: abort the in-flight request when the effect re-runs or the
    // component unmounts, preventing state updates on an unmounted component.
    return () => {
      abortRef.current?.abort()
    }
  }, [userId, doFetch])

  const refresh = useCallback(() => {
    void doFetch(false)
  }, [doFetch])

  return {
    result,
    isLoading,
    isRefreshing,
    status: result?.status ?? null,
    error,
    refresh,
  }
}
