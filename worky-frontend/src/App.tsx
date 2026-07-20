/**
 * src/App.tsx
 * ===========
 * Root application component.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Mount the WidgetShell.
 *   • Render ScreenManager inside the shell.
 *
 * This file is intentionally minimal and permanently stable.
 * It does not own screen state, auth state, or data fetching.
 * All of those concerns live in ScreenManager and the hooks it uses.
 *
 * No routing library is used. The widget has no URL-based navigation —
 * screen transitions are in-memory state only, which is compatible with
 * Electron/Tauri where there is no browser address bar.
 */

import WidgetShell from './components/shell/WidgetShell.tsx'
import ScreenManager from './components/ScreenManager.tsx'

export default function App() {
  return (
    <WidgetShell>
      <ScreenManager />
    </WidgetShell>
  )
}
