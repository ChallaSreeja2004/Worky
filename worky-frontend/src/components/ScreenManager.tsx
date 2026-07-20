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
 *   • Render DashboardScreen when authenticated.
 *   • Render SetupScreen when not authenticated.
 *   • Pass the refresh callback and connector status up to WidgetShell via
 *     a Context so the header refresh button and status dot can be wired
 *     without prop-drilling through the shell.
 *
 * PHASE EVOLUTION
 * ---------------
 * Phase 2: Auth-aware screen selection.
 * Phase 3 (current):
 *   Calls useOutlookContext and passes ConnectorResult data into DashboardScreen.
 *   Exposes refresh + connector status via OutlookStateContext for WidgetShell.
 *
 * WHY NOT IN App.tsx
 * ------------------
 * App.tsx mounts WidgetShell and renders ScreenManager. It never changes.
 * All screen-selection logic and data orchestration lives here.
 */

import { useAuth } from '../hooks/useAuth.ts'
import { useOutlookContext } from '../hooks/useOutlookContext.ts'
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

  const {
    result,
    isLoading,
    isRefreshing,
    status,
    error,
    refresh,
  } = useOutlookContext(isAuthenticated ? user?.user_id : undefined)

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
      <OutlookStateContext.Provider
        value={{
          refresh,
          connectorStatus: status,
          collectedAt: result?.collected_at ?? null,
          isRefreshing,
        }}
      >
        <DashboardScreen
          result={result}
          isLoading={isLoading}
          isRefreshing={isRefreshing}
          error={error}
        />
      </OutlookStateContext.Provider>
    )
  }

  return <SetupScreen />
}
