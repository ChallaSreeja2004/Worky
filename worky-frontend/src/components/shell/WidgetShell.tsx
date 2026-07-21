/**
 * src/components/shell/WidgetShell.tsx
 * =====================================
 * The outermost widget container.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Establish the fixed widget width (~380px) and visual chrome.
 *   • Render the widget header (app name, connection status, user name, refresh button).
 *   • Render the scrollable content area.
 *   • Render the widget footer with the last-refreshed timestamp.
 *   • Accept children (via ScreenManager) that fill the content area.
 *
 * AUTH STATE IN THE HEADER
 * ------------------------
 * The header reads isAuthenticated and user from AuthContext for display
 * purposes only — to show the user's name and the correct status dot colour.
 * This is display consumption, not logic ownership.
 *
 * CONNECTOR STATE IN THE HEADER
 * ------------------------------
 * The header reads OutlookStateContext (from ScreenManager) to:
 *   • Wire the refresh button to the connector refresh callback.
 *   • Show the correct status dot colour for connector success/partial/failed.
 *   • Display the "Updated N min ago" footer timestamp.
 * This is also display consumption — WidgetShell never calls useOutlookContext.
 *
 * ELECTRON / TAURI PORTABILITY
 * ----------------------------
 * The widget width is declared here and will match the Electron BrowserWindow
 * dimensions. The rounded corners and ring shadow are browser-rendered during
 * development; in Electron the window chrome replaces them without any code change.
 *
 * Props
 * -----
 * children — rendered inside the scrollable content area
 */

import { useState, useEffect } from 'react'
import { useAuth } from '../../hooks/useAuth.ts'
import { useOutlookState } from '../../context/outlookStateContext.ts'
import { formatRelativeTime } from '../../utils/formatters.ts'
import DemoBadge from '../shared/DemoBadge.tsx'

interface WidgetShellProps {
  children: React.ReactNode
}

// Map connector status to header dot colour.
// Falls back to amber (= not yet fetched) when status is null.
function statusDotClass(
  isAuthenticated: boolean,
  connectorStatus: 'success' | 'partial' | 'failed' | null,
): string {
  if (!isAuthenticated) return 'bg-amber-400'
  if (connectorStatus === 'success') return 'bg-green-400'
  if (connectorStatus === 'partial') return 'bg-yellow-400'
  if (connectorStatus === 'failed')  return 'bg-red-400'
  // authenticated but no fetch result yet
  return 'bg-amber-400'
}

export default function WidgetShell({ children }: WidgetShellProps) {
  const { user, isAuthenticated, logout } = useAuth()
  const { refresh, connectorStatus, collectedAt, isRefreshing } = useOutlookState()

  // C3: keep a render-tick counter that increments every 60 seconds so the
  // relative timestamp ("Updated N min ago") stays accurate without needing
  // a manual refresh.  The counter itself is not used in the render output —
  // its only job is to trigger a re-render so formatRelativeTime() is called
  // again with the current clock value.
  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  // Two-click logout safety guard: first click shows "Sign out?" label for 3 s;
  // second click within that window confirms and calls logout().
  const [logoutPending, setLogoutPending] = useState(false)
  useEffect(() => {
    if (!logoutPending) return
    const id = setTimeout(() => setLogoutPending(false), 3_000)
    return () => clearTimeout(id)
  }, [logoutPending])

  function handleLogoutClick() {
    if (!logoutPending) {
      setLogoutPending(true)
    } else {
      logout()
    }
  }

  const dotClass    = statusDotClass(isAuthenticated, connectorStatus)
  const footerLabel = collectedAt ? formatRelativeTime(collectedAt) : '—'

  return (
    <div className="w-[380px] max-w-full flex flex-col bg-white rounded-xl shadow-lg ring-1 ring-black/5 overflow-hidden">

      {/* ------------------------------------------------------------------ */}
      {/* Header                                                               */}
      {/* ------------------------------------------------------------------ */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">

        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-900 tracking-tight">
            Worky
          </span>
          {/*
           * Status dot — reflects authentication + connector state.
           * Green  = fresh Outlook data (success)
           * Yellow = partial data (some fetches failed)
           * Red    = connector failed entirely
           * Amber  = not authenticated, or authenticated but not yet fetched
           */}
          <span
            className={`h-1.5 w-1.5 rounded-full ${dotClass}`}
            aria-hidden="true"
            title={connectorStatus ?? (isAuthenticated ? 'Loading…' : 'Not connected')}
          />
        </div>

        <div className="flex items-center gap-2">
          {/* Demo mode badge — only shown when the session was created via the
              demo auth endpoint. Hidden in all real OAuth sessions. */}
          {user?.is_demo && <DemoBadge />}

          {/* Display name from the /auth/success redirect. Falls back to "—". */}
          <span className="text-xs text-gray-400 truncate max-w-[100px]">
            {user?.is_demo ? 'Demo Mode' : (user?.display_name || '—')}
          </span>

          {/*
           * Refresh button — active when authenticated.
           * Calls the combined connector + recommendations refresh via OutlookStateContext.
           * Disabled while a refresh is already in flight.
           */}
          <button
            type="button"
            aria-label="Refresh"
            title="Refresh data"
            disabled={!isAuthenticated || isRefreshing}
            onClick={isAuthenticated ? refresh : undefined}
            className={`rounded p-1 transition-colors duration-100 ${
              isAuthenticated && !isRefreshing
                ? 'text-gray-400 hover:text-gray-600 cursor-pointer'
                : 'text-gray-300 cursor-not-allowed'
            }`}
          >
            <svg
              className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"
              />
            </svg>
          </button>

          {/*
           * Logout button — shown only when authenticated.
           * First click shows "Sign out?" label for 3 s as a safety guard.
           * Second click within that window calls logout().
           */}
          {isAuthenticated && (
            <button
              type="button"
              aria-label={logoutPending ? 'Confirm sign out' : 'Sign out'}
              title={logoutPending ? 'Click again to confirm' : 'Sign out'}
              onClick={handleLogoutClick}
              className="rounded p-1 transition-colors duration-100 text-gray-400 hover:text-gray-600 cursor-pointer"
            >
              {logoutPending ? (
                <span className="text-[10px] font-medium text-red-400">Sign out?</span>
              ) : (
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9"
                  />
                </svg>
              )}
            </button>
          )}
        </div>

      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Content area — scrollable when content exceeds max height           */}
      {/* ------------------------------------------------------------------ */}
      <main className="flex-1 overflow-y-auto max-h-[520px]">
        {children}
      </main>

      {/* ------------------------------------------------------------------ */}
      {/* Footer                                                               */}
      {/* ------------------------------------------------------------------ */}
      <footer className="flex items-center justify-between px-4 py-1.5 border-t border-gray-100">
        <a
          href="https://ibm.com/products/watsonx"
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 font-medium transition-colors"
        >
          View in IBM Bob
          <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
          </svg>
        </a>
        {/* "Updated N min ago" from ConnectorResult.collected_at */}
        <span className="text-[10px] text-gray-300">{footerLabel}</span>
      </footer>

    </div>
  )
}
