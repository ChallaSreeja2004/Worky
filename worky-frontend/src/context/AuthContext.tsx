/**
 * src/context/AuthContext.tsx
 * ============================
 * Authentication provider.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Own the authenticated user state.
 *   • Hydrate from localStorage on mount so auth survives page refresh.
 *   • Expose login() and logout() to update state and localStorage.
 *   • Wrap the application tree via AuthProvider.
 *
 * WHAT THIS MODULE DOES NOT DO
 * -----------------------------
 *   • It does NOT implement OAuth.
 *   • It does NOT call the backend.
 *   • It does NOT store or handle tokens of any kind.
 *   • logout() does NOT revoke tokens — the backend owns token lifecycle.
 *
 * The context object and value type live in authContextDef.ts.
 * The useAuth hook lives in hooks/useAuth.ts.
 * These separations satisfy the fast-refresh requirement that a file
 * exports only components or only non-components.
 */

import { useEffect, useState, type ReactNode } from 'react'
import { AuthContext, type AuthContextValue } from './authContextDef.ts'
import { clearUser, loadUser, saveUser } from '../services/authService.ts'
import type { WorkyUser } from '../types/index.ts'

/**
 * Wraps the application and provides authentication state to all descendants.
 * Must be rendered above App in the tree (i.e. in main.tsx).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<WorkyUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // On first mount: hydrate from localStorage so auth survives page refresh.
  useEffect(() => {
    const stored = loadUser()
    if (stored) setUser(stored)
    setIsLoading(false)
  }, [])

  // When the API layer detects a 401 (backend token store cleared, e.g. after
  // a server restart), clear local auth state and return to SetupScreen.
  useEffect(() => {
    function handleUnauthorized() {
      clearUser()
      setUser(null)
    }
    window.addEventListener('worky:401', handleUnauthorized)
    return () => window.removeEventListener('worky:401', handleUnauthorized)
  }, [])

  function login(incoming: WorkyUser): void {
    saveUser(incoming)
    setUser(incoming)
  }

  function logout(): void {
    clearUser()
    setUser(null)
  }

  const value: AuthContextValue = {
    user,
    isAuthenticated: user !== null,
    isLoading,
    login,
    logout,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}
