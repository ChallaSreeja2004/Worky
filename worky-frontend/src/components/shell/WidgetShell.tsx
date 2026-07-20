/**
 * src/components/shell/WidgetShell.tsx
 * =====================================
 * The outermost widget container.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Establish the fixed widget width (~380px) and visual chrome.
 *   • Render the widget header (app name, connection status, refresh button).
 *   • Render the scrollable content area.
 *   • Render the widget footer.
 *   • Accept children (via ScreenManager) that fill the content area.
 *
 * ELECTRON / TAURI PORTABILITY
 * ----------------------------
 * The widget width is declared here and will match the Electron BrowserWindow
 * dimensions.  The rounded corners and ring shadow are browser-rendered during
 * development; in Electron the window chrome replaces them and these CSS
 * properties become irrelevant without any code change.
 *
 * Props
 * -----
 * children — rendered inside the scrollable content area
 */

interface WidgetShellProps {
  children: React.ReactNode
}

export default function WidgetShell({ children }: WidgetShellProps) {
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
           * Status indicator dot.
           * Amber = not yet connected (placeholder for Phase 2).
           * Phase 2 will set this to green (connected) or red (error)
           * based on the Outlook connector's ConnectorStatus.
           */}
          <span
            className="h-1.5 w-1.5 rounded-full bg-amber-400"
            aria-hidden="true"
            title="Not connected"
          />
        </div>

        <div className="flex items-center gap-2">
          {/*
           * Phase 2: replace "—" with display_name received from the
           * /auth/success redirect query parameter.
           */}
          <span className="text-xs text-gray-400 truncate max-w-[120px]">—</span>

          {/*
           * Phase 3: wire this button to call the Outlook context endpoint.
           */}
          <button
            type="button"
            aria-label="Refresh"
            title="Refresh (available in Phase 3)"
            disabled
            className="rounded p-1 text-gray-300 cursor-not-allowed"
          >
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
        {/*
         * Phase 3: replace with a formatted timestamp from
         * ConnectorResult.collected_at (e.g. "Updated 2 min ago").
         */}
        <span className="text-[10px] text-gray-300">—</span>
      </footer>

    </div>
  )
}
