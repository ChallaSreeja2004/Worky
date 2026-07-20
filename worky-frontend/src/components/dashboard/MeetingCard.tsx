/**
 * src/components/dashboard/MeetingCard.tsx
 * ==========================================
 * Single calendar event row rendered inside MeetingList.
 *
 * Display rules (from DESIGN.md)
 * ------------------------------
 *   • Subject line: text-sm font-medium text-gray-800
 *   • Organiser + time: text-xs text-gray-500
 *   • Body preview (if any): text-xs text-gray-400 — one line, truncated
 *   • Cancelled events: subject shown with line-through, muted text
 *   • Online meeting: a small "Join" link appears next to the subject
 *   • No card shadows — row-level hover only (hover:bg-gray-50)
 */

import type { CalendarEvent } from '../../types/index.ts'
import { formatMeetingTime } from '../../utils/formatters.ts'

interface MeetingCardProps {
  event: CalendarEvent
}

export default function MeetingCard({ event }: MeetingCardProps) {
  const timeLabel = formatMeetingTime(event.start, event.end, event.is_all_day)

  return (
    <div className="flex flex-col gap-0.5 px-4 py-2 hover:bg-gray-50 transition-colors duration-100">

      {/* Subject row */}
      <div className="flex items-center justify-between gap-2">
        <span
          className={`text-sm font-medium truncate ${
            event.is_cancelled ? 'line-through text-gray-400' : 'text-gray-800'
          }`}
        >
          {event.subject || '(No title)'}
        </span>

        {/* Join link — only shown for online meetings that are not cancelled */}
        {event.is_online_meeting && !event.is_cancelled && event.join_url && (
          <a
            href={event.join_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-[11px] font-medium text-blue-600 hover:text-blue-700"
          >
            Join
          </a>
        )}
      </div>

      {/* Time + organiser row
        * C8: shrink-0 on the time keeps it from collapsing, and min-w-0 on
        * the row enables the truncate class on organiser/location spans to
        * actually take effect inside a flex container. */}
      <div className="flex items-center gap-1.5 text-xs text-gray-500 min-w-0">
        <span className="shrink-0">{timeLabel}</span>
        {event.organizer_name && (
          <>
            <span className="text-gray-300 shrink-0" aria-hidden="true">·</span>
            <span className="truncate min-w-0">{event.organizer_name}</span>
          </>
        )}
        {event.location && (
          <>
            <span className="text-gray-300 shrink-0" aria-hidden="true">·</span>
            <span className="truncate min-w-0">{event.location}</span>
          </>
        )}
      </div>

    </div>
  )
}
