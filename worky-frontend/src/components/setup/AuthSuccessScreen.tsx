/**
 * src/components/setup/AuthSuccessScreen.tsx
 * ============================================
 * Transient screen that handles the /auth/success redirect from the backend.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Read user_id, display_name, email from the current URL query string.
 *   • Validate that user_id is present (minimum required field).
 *   • Call login() to persist the user and update AuthContext.
 *   • Clean the /auth/success URL from the browser history so the user
 *     cannot land here again on a manual refresh.
 *   • Render nothing visible during this transition — by the time the
 *     browser paints, ScreenManager will already be showing DashboardScreen.
 *
 * WHAT THIS COMPONENT DOES NOT DO
 * ---------------------------------
 *   • It does NOT make any API calls.
 *   • It does NOT handle tokens — none are present in the URL.
 *   • It does NOT navigate using a router library.
 *
 * FLOW
 * ----
 *   Backend redirects to: /auth/success?user_id=...&display_name=...&email=...
 *       ↓
 *   ScreenManager detects pathname === '/auth/success'
 *       ↓
 *   AuthSuccessScreen mounts, reads params, calls login()
 *       ↓
 *   AuthContext.user becomes non-null
 *       ↓
 *   ScreenManager re-renders → DashboardScreen
 *
 * ERROR HANDLING
 * --------------
 *   If user_id is missing the redirect is treated as invalid.
 *   The component calls logout() to ensure a clean state and shows
 *   SetupScreen (via the ScreenManager fallback) rather than crashing.
 */

import { useEffect } from 'react'
import { useAuth } from '../../hooks/useAuth.ts'
import { parseAuthSuccessParams } from '../../services/authService.ts'

export default function AuthSuccessScreen() {
  const { login, logout } = useAuth()

  useEffect(() => {
    const user = parseAuthSuccessParams()

    if (user) {
      login(user)
      // Replace the /auth/success URL with the root path so that a manual
      // page refresh lands at '/' (SetupScreen or DashboardScreen based on
      // stored auth) rather than re-running this callback with stale params.
      window.history.replaceState(null, '', '/')
    } else {
      // Params were missing or malformed — clear any partial auth state
      // and fall back to SetupScreen cleanly.
      logout()
      window.history.replaceState(null, '', '/')
    }
    // This effect runs exactly once on mount.
  }, [login, logout])

  // Render nothing. ScreenManager will switch away from this screen
  // immediately once login() updates AuthContext.
  return null
}
