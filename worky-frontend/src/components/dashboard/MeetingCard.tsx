/**
 * src/components/dashboard/MeetingCard.tsx
 * ==========================================
 * Compact meeting row for the supporting "Next Meeting" section.
 *
 * In the new layout, meetings are supporting information — not the hero.
 * The card shows subject, "starts in N min" countdown, location, and a
 * Join CTA for online meetings.  All in a tight single row layout.
 */

import type { CalendarEvent } from '../../types/index.ts'
import { formatMeetingTime, formatTimeUntil } from '../../utils/formatters.ts'

interface MeetingCardProps {
  event: CalendarEvent
  /** When true, show the "Starts in N min" countdown instead of the time range. */
  showCountdown?: boolean
}

export default function MeetingCard({ event, showCountdown = false }: MeetingCardProps) {
  const timeLabel     = showCountdown ? formatTimeUntil(event.start) : formatMeetingTime(event.start, event.end, event.is_all_day)
  const isInProgress  = showCountdown && formatTimeUntil(event.start) === 'In progress'

  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2 hover:bg-gray-50 transition-colors duration-100">

      {/* Left: subject + meta */}
      <div className="flex flex-col gap-0.5 min-w-0">
        <span
          className={`text-[13px] font-semibold truncate ${
            event.is_cancelled ? 'line-through text-gray-400' : 'text-gray-800'
          }`}
        >
          {event.subject || '(No title)'}
        </span>

        <div className="flex items-center gap-1.5 text-xs min-w-0">
          {/* Countdown or time range */}
          <span className={`shrink-0 font-medium ${isInProgress ? 'text-green-600' : 'text-blue-600'}`}>
            {timeLabel}
          </span>
          {event.organizer_name && (
            <>
              <span className="text-gray-300 shrink-0" aria-hidden="true">·</span>
              <span className="text-gray-500 truncate">{event.organizer_name}</span>
            </>
          )}
          {event.location && !event.organizer_name && (
            <>
              <span className="text-gray-300 shrink-0" aria-hidden="true">·</span>
              <span className="text-gray-500 truncate">{event.location}</span>
            </>
          )}
        </div>
      </div>

      {/* Right: Join CTA */}
      {event.is_online_meeting && !event.is_cancelled && event.join_url && (
        <a
          href={event.join_url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-[11px] font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded px-2.5 py-1 transition-colors duration-100"
        >
          Join
        </a>
      )}
    </div>
  )
}
