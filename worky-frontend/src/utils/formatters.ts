/**
 * src/utils/formatters.ts
 * ========================
 * Pure date/time formatting utilities for the Worky widget.
 *
 * Rules
 * -----
 *   • No React imports — these are plain TypeScript functions.
 *   • No side effects.
 *   • All functions accept ISO 8601 strings as produced by the backend.
 *   • All output is for display only — never feed these values back to an API.
 */

/**
 * Format a UTC ISO 8601 timestamp as a relative "Updated N min ago" string.
 *
 * Used in the widget footer to show when data was last successfully fetched.
 *
 * Examples
 * --------
 *   "2024-01-15T09:00:00Z"  →  "Updated just now"
 *   "2024-01-15T08:57:00Z"  →  "Updated 3 min ago"
 *   "2024-01-15T08:00:00Z"  →  "Updated 1 hr ago"
 *   "2024-01-14T09:00:00Z"  →  "Updated 1 day ago"
 */
export function formatRelativeTime(isoString: string): string {
  const then = new Date(isoString)
  if (isNaN(then.getTime())) return '—'

  const diffMs = Date.now() - then.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHr  = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)

  if (diffSec < 30)  return 'Updated just now'
  if (diffMin < 1)   return 'Updated just now'
  if (diffMin === 1) return 'Updated 1 min ago'
  if (diffMin < 60)  return `Updated ${diffMin} min ago`
  if (diffHr === 1)  return 'Updated 1 hr ago'
  if (diffHr < 24)   return `Updated ${diffHr} hr ago`
  if (diffDay === 1) return 'Updated 1 day ago'
  return `Updated ${diffDay} days ago`
}

/**
 * Format a meeting time range for display in a MeetingCard.
 *
 * Handles all-day events and normal timed events.  Both start and end are
 * ISO 8601 strings.  Times are rendered in the user's local timezone using
 * the browser's locale for the 12/24-hour preference.
 *
 * Examples
 * --------
 *   isAllDay = true                       →  "All day"
 *   start = "2024-01-15T09:00:00Z"
 *   end   = "2024-01-15T09:30:00Z"       →  "9:00 – 9:30 AM"
 *   start = "2024-01-15T13:00:00Z"
 *   end   = "2024-01-15T14:00:00Z"       →  "1:00 – 2:00 PM"
 */
export function formatMeetingTime(start: string, end: string, isAllDay: boolean): string {
  if (isAllDay) return 'All day'

  const startDate = new Date(start)
  const endDate   = new Date(end)
  if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) return '—'

  const opts: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' }
  const startStr = startDate.toLocaleTimeString(undefined, opts)
  const endStr   = endDate.toLocaleTimeString(undefined, opts)

  // If both times share the same AM/PM meridiem, strip it from the start time
  // to produce a more compact display like "9:00 – 9:30 AM".
  const startAmPm = startStr.slice(-2)
  const endAmPm   = endStr.slice(-2)
  if (startAmPm === endAmPm && /[AP]M/.test(startAmPm)) {
    const startTrimmed = startStr.slice(0, -3)  // remove " AM" or " PM"
    return `${startTrimmed} – ${endStr}`
  }

  return `${startStr} – ${endStr}`
}

/**
 * Format a received-at timestamp for display in an EmailCard.
 *
 * Shows "Today, H:MM AM/PM" for emails received today,
 * and "Mon Jan 15" for older emails.
 */
export function formatEmailTime(isoString: string): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) return '—'

  const now   = new Date()
  const today = now.toDateString() === date.toDateString()

  if (today) {
    return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  }

  return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

/**
 * Return a human-readable "starts in N min / hr" string for a future meeting.
 *
 * Examples
 * --------
 *   start is 8 minutes from now   →  "Starts in 8 min"
 *   start is 90 minutes from now  →  "Starts in 1 hr 30 min"
 *   start is in the past          →  "In progress"
 *   start is within 1 minute      →  "Starting now"
 */
export function formatTimeUntil(isoStart: string): string {
  const start = new Date(isoStart)
  if (isNaN(start.getTime())) return '—'

  const diffMs  = start.getTime() - Date.now()
  const diffMin = Math.round(diffMs / 60_000)

  if (diffMin <= 0) return 'In progress'
  if (diffMin < 1)  return 'Starting now'
  if (diffMin < 60) return `Starts in ${diffMin} min`

  const hrs = Math.floor(diffMin / 60)
  const rem = diffMin % 60
  return rem === 0
    ? `Starts in ${hrs} hr`
    : `Starts in ${hrs} hr ${rem} min`
}

/**
 * Return the hour of day (0–23) for a given ISO 8601 string in local time.
 * Used to derive a contextual greeting ("Good morning / afternoon / evening").
 */
export function localHour(): number {
  return new Date().getHours()
}
