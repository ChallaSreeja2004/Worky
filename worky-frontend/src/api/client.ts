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
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// ---------------------------------------------------------------------------
// Request interceptor
// ---------------------------------------------------------------------------
// Phase 2 will use this interceptor to attach the user_id as a query
// parameter on requests that require it (e.g. the Outlook context endpoint).
// The backend does NOT accept Bearer tokens from the frontend — token
// management is handled entirely server-side.  The frontend holds only
// user_id, display_name, and email (from the /auth/success redirect).
apiClient.interceptors.request.use(
  (config) => {
    // TODO (Phase 2): attach user_id from auth state to context endpoint calls.
    return config
  },
  (error: unknown) => Promise.reject(error),
)

// ---------------------------------------------------------------------------
// Response interceptor
// ---------------------------------------------------------------------------
// Phase 2 will handle 401 responses here and trigger re-authentication.
// For now this is a documented placeholder.
apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    // TODO (Phase 2): detect 401 and redirect to setup screen.
    return Promise.reject(error)
  },
)

export default apiClient
