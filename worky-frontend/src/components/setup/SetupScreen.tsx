/**
 * src/components/setup/SetupScreen.tsx
 * ======================================
 * Onboarding screen shown before the user has authenticated.
 *
 * PRODUCTION PATH (unchanged)
 * ---------------------------
 * Clicking "Connect Outlook" navigates the browser to the backend login
 * endpoint, which starts the Microsoft OAuth 2.0 PKCE flow.
 * The frontend does NOT construct any OAuth URLs — it simply redirects to
 * /api/v1/auth/login and the backend handles everything else.
 *
 * DEMO PATH (new)
 * ---------------
 * Clicking "Continue in Demo Mode" calls POST /api/v1/auth/demo on the backend
 * and immediately logs in with the returned synthetic identity.  No OAuth flow,
 * no Microsoft credentials required.  This path is only available when the
 * backend is running with CONNECTOR_MODE=demo.
 *
 * If the demo endpoint is unreachable (e.g. backend is in production mode) the
 * button shows a brief error message instead of crashing.
 */

import { useState } from 'react'
import { useAuth } from '../../hooks/useAuth.ts'
import { postDemoAuth } from '../../api/auth.ts'

export default function SetupScreen() {
  const { login } = useAuth()
  const [demoError, setDemoError] = useState<string | null>(null)
  const [demoLoading, setDemoLoading] = useState(false)

  function handleLogin() {
    // Navigate the entire browser window to the backend login endpoint.
    // The backend generates the PKCE pair and redirects to Microsoft.
    // On success Microsoft redirects back to the backend callback, which
    // then redirects here to /auth/success with user identity params.
    window.location.href = `${import.meta.env.VITE_API_BASE_URL as string}/api/v1/auth/login`
  }

  async function handleDemoLogin() {
    setDemoLoading(true)
    setDemoError(null)
    try {
      const user = await postDemoAuth()
      login(user)
    } catch {
      setDemoError('Demo mode is not available. Ensure the backend is running with CONNECTOR_MODE=demo.')
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center gap-5 py-8 px-6">

      {/* App icon */}
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50">
        <svg
          className="h-6 w-6 text-blue-600"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"
          />
        </svg>
      </div>

      <div className="text-center">
        <p className="text-sm font-medium text-gray-800">
          Connect your workspace
        </p>
        <p className="mt-1 text-xs text-gray-400 leading-relaxed">
          Sign in with Microsoft to see your meetings and emails.
        </p>
      </div>

      {/* Primary action — unchanged production OAuth flow */}
      <button
        type="button"
        onClick={handleLogin}
        className="rounded-md bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors duration-100"
      >
        Connect Outlook
      </button>

      {/* Divider */}
      <div className="flex items-center gap-3 w-full max-w-[220px]">
        <span className="flex-1 h-px bg-gray-100" aria-hidden="true" />
        <span className="text-[10px] font-medium text-gray-300 uppercase tracking-wide">or</span>
        <span className="flex-1 h-px bg-gray-100" aria-hidden="true" />
      </div>

      {/* Demo mode entry point */}
      <div className="flex flex-col items-center gap-1.5">
        <button
          type="button"
          onClick={handleDemoLogin}
          disabled={demoLoading}
          className={`rounded-md border border-gray-200 px-5 py-2 text-sm font-medium transition-colors duration-100 ${
            demoLoading
              ? 'text-gray-300 cursor-not-allowed'
              : 'text-gray-500 hover:text-gray-700 hover:border-gray-300 cursor-pointer'
          }`}
        >
          {demoLoading ? 'Starting demo…' : 'Continue in Demo Mode'}
        </button>
        <p className="text-[10px] text-gray-300 text-center max-w-[200px] leading-relaxed">
          Uses representative Outlook data. No Microsoft account required.
        </p>
      </div>

      {/* Demo error message */}
      {demoError && (
        <p className="text-[11px] text-red-500 text-center max-w-[220px] leading-relaxed" role="alert">
          {demoError}
        </p>
      )}

    </div>
  )
}
