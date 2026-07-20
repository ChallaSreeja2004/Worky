/**
 * src/components/dashboard/MeetingList.tsx
 * ==========================================
 * Meetings section rendered inside DashboardScreen.
 *
 * Handles three states:
 *   loading    — shows LoadingSpinner while first fetch is in flight
 *   empty      — shows a calm "No meetings today" message
 *   populated  — renders one MeetingCard per calendar event
 *
 * Does not handle error state — ScreenManager passes an ErrorBanner
 * into DashboardScreen when the connector status is "failed".
 */

import type { CalendarEvent } from '../../types/index.ts'
import LoadingSpinner from '../shared/LoadingSpinner.tsx'
import MeetingCard from './MeetingCard.tsx'

interface MeetingListProps {
  events: CalendarEvent[]
  isLoading: boolean
}

export default function MeetingList({ events, isLoading }: MeetingListProps) {
  if (isLoading) {
    return (
      <div className="px-4 py-3">
        <LoadingSpinner />
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <p className="px-4 py-2 text-xs text-gray-400">No meetings today.</p>
    )
  }

  return (
    <div className="flex flex-col">
      {events.map((event) => (
        <MeetingCard key={event.id} event={event} />
      ))}
    </div>
  )
}
