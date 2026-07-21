/**
 * src/components/ScreenManager.tsx
 * ==================================
 * Controls which screen is currently active inside the widget shell.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Read authentication state from useAuth.
 *   • Detect the /auth/success redirect path and render AuthSuccessScreen.
 *   • Show a loading state while auth is being initialised from localStorage.
 *   • Own the useOutlookContext hook and pass its state as props to DashboardScreen.
 *   • Own the useRecommendations hook and pass its state as props to DashboardScreen.
 *   • Render DashboardScreen when authenticated.
 *   • Render SetupScreen when not authenticated.
 *   • Pass the refresh callback and connector status up to WidgetShell via
 *     a Context so the header refresh button and status dot can be wired
 *     without prop-drilling through the shell.
 *
 * PHASE EVOLUTION
 * ---------------
 * Phase 2: Auth-aware screen selection.
 * Phase 3: Calls useOutlookContext and passes ConnectorResult data into DashboardScreen.
 *          Exposes refresh + connector status via OutlookStateContext for WidgetShell.
 * Phase 6 (current):
 *   Calls useRecommendations and passes RecommendationSet into DashboardScreen.
 *
 * WHY NOT IN App.tsx
 * ------------------
 * App.tsx mounts WidgetShell and renders ScreenManager. It never changes.
 * All screen-selection logic and data orchestration lives here.
 */

import { useCallback, useMemo } from 'react'
import { useAuth } from '../hooks/useAuth.ts'
import { useOutlookContext } from '../hooks/useOutlookContext.ts'
import { useRecommendations } from '../hooks/useRecommendations.ts'
import { OutlookStateContext } from '../context/outlookStateContext.ts'
import AuthSuccessScreen from './setup/AuthSuccessScreen.tsx'
import DashboardScreen from './dashboard/DashboardScreen.tsx'
import SetupScreen from './setup/SetupScreen.tsx'
import LoadingSpinner from './shared/LoadingSpinner.tsx'

// ---------------------------------------------------------------------------
// ScreenManager
// ---------------------------------------------------------------------------

export default function ScreenManager() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()

  const userId  = isAuthenticated ? user?.user_id  : undefined
  const isDemo  = user?.is_demo === true

  const {
    result,
    isLoading: outlookLoading,
    isRefreshing: outlookRefreshing,
    status,
    error: outlookError,
    refresh: refreshOutlook,
  } = useOutlookContext(userId, isDemo)

  const {
    data: recommendations,
    isLoading: recsLoading,
    isRefreshing: recsRefreshing,
    error: recsError,
    refresh: refreshRecs,
  } = useRecommendations(userId)

  // Combined refresh: refreshes both Outlook context and recommendations.
  // In demo mode refreshOutlook() is a no-op (the hook guard blocks the
  // /connectors/outlook/context request); only recommendations are refreshed.
  // Memoized so the OutlookStateContext value object reference is stable
  // across renders that don't change the underlying refresh callbacks.
  const handleRefresh = useCallback(() => {
    refreshOutlook()
    refreshRecs()
  }, [refreshOutlook, refreshRecs])

  const isRefreshing = outlookRefreshing || recsRefreshing

  // Memoize the context value so OutlookStateContext consumers (WidgetShell)
  // do not re-render on every ScreenManager state update — only when the
  // relevant values actually change.
  const outlookStateValue = useMemo(
    () => ({
      refresh: handleRefresh,
      connectorStatus: status,
      collectedAt: result?.collected_at ?? null,
      isRefreshing,
    }),
    [handleRefresh, status, result, isRefreshing],
  )

  // The backend redirects to /auth/success after a successful OAuth login.
  if (window.location.pathname === '/auth/success') {
    return <AuthSuccessScreen />
  }

  // While localStorage is being read on mount, show a minimal loading state
  // so the widget doesn't flash SetupScreen before discovering stored auth.
  if (authLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }

  if (isAuthenticated) {
    return (
      <OutlookStateContext.Provider value={outlookStateValue}>
        <DashboardScreen
          result={result}
          isLoading={outlookLoading}
          isRefreshing={isRefreshing}
          error={outlookError}
          recommendations={recommendations?.recommendations ?? null}
          recsLoading={recsLoading}
          recsError={recsError}
          displayName={isDemo ? 'Demo User' : (user?.display_name || undefined)}
        />
      </OutlookStateContext.Provider>
    )
  }

  return <SetupScreen />
}
