/**
 * src/components/ScreenManager.tsx
 * ==================================
 * Controls which screen is currently active inside the widget shell.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Own the active-screen decision.
 *   • Render the correct screen based on application state.
 *   • Be the single place that changes when Phase 2 adds authentication.
 *
 * PHASE EVOLUTION
 * ---------------
 * Phase 1 (current):
 *   Always renders SetupScreen.
 *
 * Phase 2 will:
 *   • Import useAuth hook
 *   • Render SetupScreen when unauthenticated
 *   • Render DashboardScreen when authenticated
 *   • Handle the /auth/success redirect query params here
 *   Only this file changes — App.tsx and WidgetShell remain stable.
 *
 * Phase 3 will:
 *   • Pass Outlook context data down into DashboardScreen as props
 *   Only this file (and DashboardScreen) change.
 *
 * WHY NOT IN App.tsx
 * ------------------
 * Keeping screen-selection logic here means App.tsx is permanently stable
 * at exactly two responsibilities: mount WidgetShell, render ScreenManager.
 * Future phases touch only ScreenManager, never the root.
 */

import SetupScreen from './setup/SetupScreen.tsx'

export default function ScreenManager() {
  /*
   * Phase 2: import useAuth and replace the unconditional SetupScreen
   * with a conditional based on auth state:
   *
   *   const { isAuthenticated } = useAuth()
   *   return isAuthenticated ? <DashboardScreen /> : <SetupScreen />
   */
  return <SetupScreen />
}
