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
  const { user, isAuthenticated } = useAuth()
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
          {/* Display name from the /auth/success redirect. Falls back to "—". */}
          <span className="text-xs text-gray-400 truncate max-w-[120px]">
            {user?.display_name || '—'}
          </span>

          {/*
           * Refresh button — active when authenticated.
           * Calls the connector refresh callback via OutlookStateContext.
           * Disabled while a refresh is already in flight.
           */}
          <button
            type="button"
            aria-label="Refresh"
            title="Refresh Outlook data"
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
        </div>

      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Content area — scrollable when content exceeds max height           */}
      {/* ------------------------------------------------------------------ */}
      <main className="flex-1 overflow-y-auto max-h-[560px]">
        {children}
      </main>

      {/* ------------------------------------------------------------------ */}
      {/* Footer                                                               */}
      {/* ------------------------------------------------------------------ */}
      <footer className="flex items-center justify-between px-4 py-1.5 border-t border-gray-100">
        <span className="text-[10px] text-gray-300 font-medium tracking-wide uppercase">
          Powered by IBM Bob
        </span>
        {/* "Updated N min ago" from ConnectorResult.collected_at */}
        <span className="text-[10px] text-gray-300">{footerLabel}</span>
      </footer>

    </div>
  )
}
