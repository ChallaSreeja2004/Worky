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
 *
 * STRICT MODE / DOUBLE-INVOCATION NOTE
 * -------------------------------------
 *   React.StrictMode in development intentionally mounts, unmounts, and
 *   remounts every component to surface side-effect bugs.  This causes
 *   useEffect to fire twice.
 *
 *   The original code called window.history.replaceState(null, '', '/') on
 *   the first run, which wiped the query string from window.location.search.
 *   On the second run, parseAuthSuccessParams() read an empty search string,
 *   returned null, and the else-branch called logout() — undoing the login
 *   that had just succeeded.
 *
 *   The fix: parse the params exactly once, before replaceState is called,
 *   and guard the effect body with a ref so the auth-mutating logic (login /
 *   logout) executes only on the first invocation regardless of StrictMode
 *   double-firing or any future remount.
 */

import { useEffect, useRef } from 'react'
import { useAuth } from '../../hooks/useAuth.ts'
import { parseAuthSuccessParams } from '../../services/authService.ts'

export default function AuthSuccessScreen() {
  const { login, logout } = useAuth()

  // Parse the query params immediately at render time, before any effect
  // runs or replaceState cleans the URL.  This snapshot is stable across
  // StrictMode double-invocations because the URL only changes inside the
  // effect — and only after the snapshot has already been taken.
  const userSnapshot = parseAuthSuccessParams()

  // Guard: ensure the auth mutation (login/logout) and URL cleanup happen
  // exactly once even when StrictMode mounts this component twice.
  const committed = useRef(false)

  useEffect(() => {
    if (committed.current) return
    committed.current = true

    if (userSnapshot) {
      login(userSnapshot)
    } else {
      // Params were missing or malformed — clear any partial auth state
      // and fall back to SetupScreen cleanly.
      logout()
    }

    // Clean the /auth/success URL from history after committing auth state.
    // A manual page refresh will now land at '/' and hydrate from localStorage.
    window.history.replaceState(null, '', '/')
  }, [login, logout, userSnapshot])

  // Render nothing. ScreenManager will switch away from this screen
  // immediately once login() updates AuthContext.
  return null
}
