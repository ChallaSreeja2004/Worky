/**
 * src/hooks/useAuth.ts
 * =====================
 * Custom hook for consuming authentication state.
 *
 * Separated from AuthContext.tsx so that the provider file exports only
 * the AuthProvider component — satisfying the React fast-refresh constraint
 * that a file should export only components or only non-components.
 *
 * USAGE
 * -----
 *   import { useAuth } from '../hooks/useAuth.ts'
 *
 *   const { user, isAuthenticated, isLoading, login, logout } = useAuth()
 */

import { useContext } from 'react'
import { AuthContext, type AuthContextValue } from '../context/authContextDef.ts'

/**
 * Access authentication state from any component inside AuthProvider.
 *
 * Throws if called outside of an AuthProvider — this is always a programmer
 * error and should fail loudly in development.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth must be used inside an AuthProvider.')
  }
  return ctx
}
