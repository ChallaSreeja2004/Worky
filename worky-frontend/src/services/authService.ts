/**
 * src/services/authService.ts
 * ============================
 * Authentication persistence and URL parameter parsing.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Read and write the authenticated user to localStorage.
 *   • Parse the user identity query parameters from the /auth/success URL.
 *   • Provide a clean logout that wipes only auth-related storage.
 *
 * WHAT THIS MODULE DOES NOT DO
 * -----------------------------
 *   • It does NOT make any HTTP requests.
 *   • It does NOT implement OAuth logic.
 *   • It does NOT store or read tokens of any kind.
 *   • It does NOT import from React — it is plain TypeScript.
 *
 * The backend passes exactly three values in the /auth/success redirect:
 *   user_id, display_name, email
 * No access_token, no refresh_token, no expires_at.
 */

import type { WorkyUser } from '../types/index.ts'

// The localStorage key under which the user object is persisted.
// Namespaced to avoid collisions with other applications running on the
// same origin during development.
const STORAGE_KEY = 'worky.user'

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

/**
 * Persist the authenticated user to localStorage.
 * Overwrites any existing entry.
 */
export function saveUser(user: WorkyUser): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(user))
}

/**
 * Retrieve the persisted user from localStorage.
 * Returns null if no user has been saved or if the stored value is corrupt.
 */
export function loadUser(): WorkyUser | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    // Validate that the stored object has the three required fields.
    if (
      typeof parsed.user_id === 'string' &&
      typeof parsed.display_name === 'string' &&
      typeof parsed.email === 'string'
    ) {
      return {
        user_id: parsed.user_id,
        display_name: parsed.display_name,
        email: parsed.email,
      }
    }
    // Stored data is missing required fields — treat as no user.
    clearUser()
    return null
  } catch {
    // Stored value is not valid JSON — treat as no user.
    clearUser()
    return null
  }
}

/**
 * Remove the persisted user from localStorage (logout).
 */
export function clearUser(): void {
  localStorage.removeItem(STORAGE_KEY)
}

// ---------------------------------------------------------------------------
// URL parameter parsing
// ---------------------------------------------------------------------------

/**
 * Parse WorkyUser fields from the /auth/success query string.
 *
 * The backend encodes user_id, display_name, and email as URL-encoded
 * query parameters in the redirect to FRONTEND_URL/auth/success.
 * This function reads window.location.search and returns a WorkyUser
 * if all three required fields are present and non-empty.
 *
 * Returns null if any required field is missing or empty — this indicates
 * a malformed redirect and should not be treated as a successful login.
 */
export function parseAuthSuccessParams(): WorkyUser | null {
  const params = new URLSearchParams(window.location.search)
  const user_id = params.get('user_id')?.trim() ?? ''
  const display_name = params.get('display_name')?.trim() ?? ''
  const email = params.get('email')?.trim() ?? ''

  if (!user_id) return null

  return { user_id, display_name, email }
}
