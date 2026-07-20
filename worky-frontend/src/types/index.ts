/**
 * src/types/index.ts
 * ==================
 * TypeScript mirrors of backend Pydantic models.
 *
 * Rules:
 *   • Every type must have a corresponding backend model.
 *   • Field names exactly match the backend's model_dump() output (snake_case).
 *   • Do not define types that have no backend equivalent.
 */

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/**
 * The authenticated user identity held by the frontend.
 *
 * These three fields are the only values passed by the backend in the
 * /auth/success redirect query parameters.  No tokens, no expiry, no Graph
 * data are ever present on the frontend.
 *
 * Mirrors the non-sensitive subset of app/auth/models.py AuthorizationResponse.
 */
export interface WorkyUser {
  /** Microsoft Azure AD object ID — the stable Worky-internal user identifier. */
  user_id: string
  /** Full name from the enterprise directory. Empty string if unavailable. */
  display_name: string
  /** Enterprise email address. Empty string if unavailable. */
  email: string
}

// ---------------------------------------------------------------------------
// Connectors — shared
// Mirrors: app/connectors/models.py
// ---------------------------------------------------------------------------

/**
 * Terminal status of a connector's data collection attempt.
 * Values are lowercase strings exactly as returned by the backend.
 */
export type ConnectorStatus = 'success' | 'partial' | 'failed'

/**
 * Standard output contract of every backend connector.
 * Mirrors: app/connectors/models.py ConnectorResult
 *
 * Generic over T so each API call site can specify the concrete data
 * payload type (e.g. ConnectorResult<OutlookData>).  The backend
 * response shape is unchanged — only the frontend type is narrowed.
 */
export interface ConnectorResult<T = unknown> {
  source: string
  status: ConnectorStatus
  /** UTC ISO 8601 timestamp when the connector finished data collection. */
  collected_at: string
  data: T
  errors: string[]
  metadata: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Outlook connector
// Mirrors: app/connectors/outlook/models.py
// ---------------------------------------------------------------------------

/**
 * Normalised Outlook payload inside ConnectorResult.data.
 * Mirrors: app/connectors/outlook/models.py OutlookContext
 *
 * Note: user is always null in the current backend implementation —
 * the router does not call get_current_user().  Do not rely on it.
 */
export interface OutlookData {
  user: null
  calendar_events: CalendarEvent[]
  emails: Email[]
}

/**
 * Normalised Microsoft 365 calendar event.
 * Mirrors: app/connectors/outlook/models.py CalendarEvent
 */
export interface CalendarEvent {
  id: string
  subject: string
  /** ISO 8601 start datetime string. */
  start: string
  /** ISO 8601 end datetime string. */
  end: string
  location: string
  organizer_name: string
  organizer_email: string
  is_all_day: boolean
  is_cancelled: boolean
  is_online_meeting: boolean
  /** Online meeting join URL.  Empty string when not an online meeting. */
  join_url: string
  body_preview: string
}

/**
 * Normalised Microsoft 365 email message.
 * Mirrors: app/connectors/outlook/models.py Email
 */
export interface Email {
  id: string
  subject: string
  sender_name: string
  sender_email: string
  /** ISO 8601 received datetime string. */
  received_at: string
  is_read: boolean
  /** "low" | "normal" | "high" */
  importance: string
  body_preview: string
  has_attachments: boolean
}
