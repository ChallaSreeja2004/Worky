/**
 * src/context/authContextDef.ts
 * ==============================
 * AuthContext definition and value type.
 *
 * Separated from AuthContext.tsx (which exports only the AuthProvider
 * component) so that both the provider and the useAuth hook can import
 * the context object without triggering the fast-refresh lint rule that
 * prohibits mixing component and non-component exports in one file.
 */

import { createContext } from 'react'
import type { WorkyUser } from '../types/index.ts'

export interface AuthContextValue {
  /** The authenticated user, or null if not authenticated. */
  user: WorkyUser | null
  /** True when the user is authenticated. */
  isAuthenticated: boolean
  /**
   * True during the brief initial mount while localStorage is being read.
   * ScreenManager shows a loading state until this becomes false.
   */
  isLoading: boolean
  /**
   * Persist a user as authenticated.
   * Called by AuthSuccessScreen after parsing the /auth/success redirect params.
   */
  login: (user: WorkyUser) => void
  /**
   * Clear the authenticated user and return to SetupScreen.
   * Does NOT call the backend — token revocation is the backend's concern.
   */
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
