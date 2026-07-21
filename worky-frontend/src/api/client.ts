/**
 * src/api/client.ts
 * =================
 * Centralised Axios instance for all backend communication.
 *
 * RESPONSIBILITIES
 * ----------------
 *   • Configure the base URL from the VITE_API_BASE_URL environment variable.
 *   • Set a consistent default timeout for all requests.
 *   • Apply default JSON headers.
 *   • Provide a single intercept point for future authentication headers
 *     (Phase 2) and response error normalisation.
 *
 * WHAT THIS MODULE DOES NOT DO
 * -----------------------------
 *   • It does NOT import from any feature module (hooks, components, types).
 *   • It does NOT store authentication state.
 *   • It does NOT call any API endpoints.
 *
 * ELECTRON / TAURI PORTABILITY
 * ----------------------------
 * All API communication is isolated here.  When porting to Electron, only
 * this file needs to change (e.g., replacing axios calls with IPC messages
 * to the main process).  Every hook and component that calls the API does so
 * through functions defined in src/api/ — never through direct axios calls.
 */

import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL as string,
  // 60 s — Bob CLI generation takes 15–30 s; the backend BobCLIService timeout
  // is 120 s.  15 s (the previous value) was shorter than Bob's response time,
  // causing every recommendations request to be cancelled before the backend
  // could reply.  60 s gives Bob headroom while still providing a hard ceiling
  // well under the backend's own 120 s timeout.
  timeout: 60_000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// ---------------------------------------------------------------------------
// Request interceptor
// ---------------------------------------------------------------------------
// user_id is passed as a query parameter by each individual API call that
// requires it (e.g. fetchOutlookContext).  No Bearer tokens are ever sent —
// the backend owns the full token lifecycle server-side.
apiClient.interceptors.request.use(
  (config) => config,
  (error: unknown) => Promise.reject(error),
)

// ---------------------------------------------------------------------------
// Response interceptor
// ---------------------------------------------------------------------------
// On a 401 response the backend's InMemoryTokenRepository has been cleared
// (e.g. server restart).  Dispatch a custom event so AuthProvider can clear
// local state and return the user to SetupScreen without importing React here.
apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (
      typeof error === 'object' &&
      error !== null &&
      'response' in error &&
      (error as { response?: { status?: number } }).response?.status === 401
    ) {
      window.dispatchEvent(new CustomEvent('worky:401'))
    }
    return Promise.reject(error)
  },
)

export default apiClient
