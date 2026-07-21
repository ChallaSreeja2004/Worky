/**
 * src/components/dashboard/DashboardScreen.tsx
 * ==============================================
 * Worky AI-companion widget — compact desktop layout.
 *
 * LAYOUT HIERARCHY  (matches the Worky proposal image)
 * ----------------
 *   1. Greeting header          — "Good morning, Alex!" + today's date
 *   2. Today's Priorities       — top-3 numbered list + "Why these?" + "+N more"
 *   3. Upcoming Meetings        — next 2 meetings, compact 1-line rows
 *   4. Blockers                 — 1-2 blocking items derived from recommendations
 *   5. Pending Reviews          — 1-2 PR/review items derived from recommendations
 *   6. Learning                 — 1-2 learning items derived from recommendations
 *   Footer                      — "View in IBM Bob" external link
 *
 * DESIGN INTENT
 * -------------
 * Every section is 1–2 lines tall.  The full widget fits within ~520 px with
 * no scrolling in the typical case.  Recommendations are not displayed as
 * individual cards — they are summarised into thematic sections derived by
 * keyword matching on title/description.
 *
 * DATA CONTRACT
 * -------------
 * Presentation-only.  All data arrives as props from ScreenManager.
 */

import { useMemo } from 'react'
import type { CalendarEvent, ConnectorResult, OutlookData, Recommendation } from '../../types/index.ts'
import RecommendationList from './RecommendationList.tsx'
import LoadingSpinner from '../shared/LoadingSpinner.tsx'
import ErrorBanner from '../shared/ErrorBanner.tsx'
import StatusBadge from '../shared/StatusBadge.tsx'
import { localHour, formatMeetingTime, formatTimeUntil } from '../../utils/formatters.ts'

// NOTE: The heuristic categorisation helpers (blockers / pendingReviews / learningItems)
// below are the sole location of keyword-matching logic.  When the backend adds a
// structured `section` field to Recommendation, replace only those three functions.

interface DashboardScreenProps {
  result: ConnectorResult<OutlookData> | null
  isLoading: boolean
  isRefreshing: boolean
  error: string | null
  recommendations: Recommendation[] | null
  recsLoading: boolean
  recsError: string | null
  displayName?: string
}

// ---------------------------------------------------------------------------
// Greeting helpers
// ---------------------------------------------------------------------------

function greetingText(name: string | undefined): string {
  const hour = localHour()
  const salutation =
    hour < 12 ? 'Good morning' :
    hour < 17 ? 'Good afternoon' :
                'Good evening'
  const first = name ? name.split(' ')[0] : null
  return first ? `${salutation}, ${first}!` : `${salutation}!`
}

function todayLabel(): string {
  return new Date().toLocaleDateString(undefined, {
    weekday: 'long', day: 'numeric', month: 'long',
  })
}

// ---------------------------------------------------------------------------
// Meeting helpers
// ---------------------------------------------------------------------------

function upcomingMeetings(events: CalendarEvent[], limit: number): CalendarEvent[] {
  const now = Date.now()
  return events
    .filter((e) => !e.is_cancelled && new Date(e.end).getTime() > now)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
    .slice(0, limit)
}

// ---------------------------------------------------------------------------
// Recommendation categorisation
// Classifies recs by keyword matching on title + description.
// Each rec only appears in at most one supporting section.
// ---------------------------------------------------------------------------

function matchesAny(r: Recommendation, keywords: string[]): boolean {
  const haystack = `${r.title} ${r.description}`.toLowerCase()
  return keywords.some((k) => haystack.includes(k))
}

function blockers(recs: Recommendation[], top3Priorities: Recommendation[]): Recommendation[] {
  const top3Set = new Set(top3Priorities.map((r) => r.priority))
  return recs
    .filter((r) => !top3Set.has(r.priority))
    .filter((r) => matchesAny(r, ['block', 'fail', 'broke', 'broken', 'urgent', 'critical', 'issue', 'error']))
    .slice(0, 2)
}

function pendingReviews(recs: Recommendation[], top3Priorities: Recommendation[]): Recommendation[] {
  const top3Set = new Set(top3Priorities.map((r) => r.priority))
  return recs
    .filter((r) => !top3Set.has(r.priority))
    .filter((r) => matchesAny(r, ['review', 'pr #', 'pull request', 'pr-', 'approve', 'approving', 'merge']))
    .slice(0, 2)
}

function learningItems(recs: Recommendation[], top3Priorities: Recommendation[]): Recommendation[] {
  const top3Set = new Set(top3Priorities.map((r) => r.priority))
  return recs
    .filter((r) => !top3Set.has(r.priority))
    .filter((r) => matchesAny(r, ['learn', 'course', 'badge', 'training', 'certification', 'skill', 'module', 'path']))
    .slice(0, 2)
}

// ---------------------------------------------------------------------------
// Shared compact section chrome
// ---------------------------------------------------------------------------

interface CompactSectionProps {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
  /** Optional chevron link — shown on the right of the section heading */
  href?: string
}

function CompactSection({ icon, title, children, href }: CompactSectionProps) {
  return (
    <div className="px-4 py-2.5 border-b border-gray-100 last:border-b-0">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-gray-400 flex items-center">{icon}</span>
          <span className="text-xs font-semibold text-gray-700">{title}</span>
        </div>
        {href && (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open ${title} in IBM Bob`}
            className="text-gray-300 hover:text-gray-500 transition-colors"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
            </svg>
          </a>
        )}
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SVG icons (inline, no external dependency)
// ---------------------------------------------------------------------------

function CalendarIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
    </svg>
  )
}

function BlockerIcon() {
  return (
    <svg className="h-3.5 w-3.5 text-red-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
    </svg>
  )
}

function ReviewIcon() {
  return (
    <svg className="h-3.5 w-3.5 text-purple-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5" />
    </svg>
  )
}

function LearnIcon() {
  return (
    <svg className="h-3.5 w-3.5 text-indigo-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.292m0-14.25v14.25" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Compact recommendation line (used inside supporting sections)
// ---------------------------------------------------------------------------

function RecLine({ rec }: { rec: Recommendation }) {
  return (
    <div className="flex items-baseline justify-between gap-1.5 min-w-0">
      <span className="text-[12px] text-gray-700 truncate">{rec.title}</span>
      {rec.action_url && (
        <a
          href={rec.action_url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-[10px] text-blue-600 hover:text-blue-700 font-medium"
        >
          Open
        </a>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Compact meeting row — 1 line (time + title + Join)
// ---------------------------------------------------------------------------

function MeetingRow({ event }: { event: CalendarEvent }) {
  const timeLabel = formatMeetingTime(event.start, event.end, event.is_all_day)
  const countdown = formatTimeUntil(event.start)
  const isInProgress = countdown === 'In progress'

  return (
    <div className="flex items-center justify-between gap-2 min-w-0">
      <div className="flex items-baseline gap-2 min-w-0 flex-1">
        <span className={`shrink-0 text-[11px] font-medium tabular-nums ${isInProgress ? 'text-green-600' : 'text-gray-500'}`}>
          {isInProgress ? 'Now' : timeLabel.split(' – ')[0]}
        </span>
        <span className="text-[12px] font-medium text-gray-800 truncate">{event.subject}</span>
      </div>
      {event.is_online_meeting && !event.is_cancelled && event.join_url && (
        <a
          href={event.join_url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-[10px] font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded px-1.5 py-0.5"
        >
          Join
        </a>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// DashboardScreen
// ---------------------------------------------------------------------------

const IBM_BOB_URL = 'https://ibm.com/products/watsonx'

export default function DashboardScreen({
  result,
  isLoading,
  isRefreshing,
  error,
  recommendations,
  recsLoading,
  recsError,
  displayName,
}: DashboardScreenProps) {
  const recItems       = recommendations ?? []
  const recsAreLoading = recsLoading || (recommendations === null && !recsError)

  // Depend on `recommendations` (the prop) not `recItems` (a new [] on every render)
  // so these memos only recompute when the actual data changes.
  const top3 = useMemo(
    () => (recommendations ?? []).slice(0, 3),
    [recommendations],
  )

  const meetings = useMemo(() => {
    const events: CalendarEvent[] = result?.data.calendar_events ?? []
    return upcomingMeetings(events, 2)
  }, [result])

  const blockItems  = useMemo(
    () => blockers(recommendations ?? [], top3),
    [recommendations, top3],
  )
  const reviewItems = useMemo(
    () => pendingReviews(recommendations ?? [], top3),
    [recommendations, top3],
  )
  const learnItems  = useMemo(
    () => learningItems(recommendations ?? [], top3),
    [recommendations, top3],
  )

  return (
    <div className="flex flex-col">

      {/* ------------------------------------------------------------------ */}
      {/* Error / status banners                                               */}
      {/* ------------------------------------------------------------------ */}

      {error && !isLoading && (
        <div className="px-4 pt-3 pb-1">
          <ErrorBanner message="Could not load Outlook data. Check your connection and try refreshing." />
        </div>
      )}

      {result && result.status !== 'success' && (
        <div className="px-4 pt-2 pb-1 flex items-center gap-2">
          <StatusBadge status={result.status} />
          {result.errors.length > 0 && (
            <span className="text-xs text-gray-500 truncate">{result.errors[0]}</span>
          )}
        </div>
      )}

      {isRefreshing && (
        <div className="px-4 pt-1">
          <p className="text-[10px] text-gray-400">Refreshing…</p>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Greeting header                                                      */}
      {/* ------------------------------------------------------------------ */}

      <div className="px-4 pt-3.5 pb-3 border-b border-gray-100 flex items-start justify-between">
        <div>
          <p className="text-[15px] font-bold text-gray-900 leading-snug">
            {greetingText(displayName)}
          </p>
          <p className="text-[11px] text-gray-400 mt-0.5">{todayLabel()}</p>
        </div>
        {/* Sun emoji for morning, moon for evening */}
        <span className="text-xl mt-0.5" aria-hidden="true">
          {localHour() < 18 ? '☀️' : '🌙'}
        </span>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Today's Priorities                                                   */}
      {/* ------------------------------------------------------------------ */}

      <div className="px-4 py-2.5 border-b border-gray-100">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-bold text-gray-800">Today's Priorities</span>
          <a
            href={IBM_BOB_URL}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] font-medium text-blue-600 hover:text-blue-700"
          >
            Why these?
          </a>
        </div>
        <RecommendationList
          items={recItems}
          isLoading={recsAreLoading}
          error={recsError}
        />
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Upcoming Meetings                                                    */}
      {/* ------------------------------------------------------------------ */}

      <CompactSection icon={<CalendarIcon />} title="Upcoming Meetings" href={IBM_BOB_URL}>
        {isLoading ? (
          <div className="py-1"><LoadingSpinner /></div>
        ) : meetings.length > 0 ? (
          <div className="flex flex-col gap-1">
            {meetings.map((e) => <MeetingRow key={e.id} event={e} />)}
          </div>
        ) : (
          <p className="text-[12px] text-gray-400">No upcoming meetings today.</p>
        )}
      </CompactSection>

      {/* ------------------------------------------------------------------ */}
      {/* Blockers                                                             */}
      {/* ------------------------------------------------------------------ */}

      <CompactSection icon={<BlockerIcon />} title="Blockers" href={IBM_BOB_URL}>
        {recsAreLoading ? (
          <div className="py-0.5"><LoadingSpinner /></div>
        ) : blockItems.length > 0 ? (
          <div className="flex flex-col gap-0.5">
            {blockItems.map((r) => <RecLine key={r.priority} rec={r} />)}
          </div>
        ) : (
          <p className="text-[12px] text-gray-400">No blockers detected.</p>
        )}
      </CompactSection>

      {/* ------------------------------------------------------------------ */}
      {/* Pending Reviews                                                      */}
      {/* ------------------------------------------------------------------ */}

      <CompactSection icon={<ReviewIcon />} title={`Pending Reviews${reviewItems.length > 0 ? ` (${reviewItems.length})` : ''}`} href={IBM_BOB_URL}>
        {recsAreLoading ? (
          <div className="py-0.5"><LoadingSpinner /></div>
        ) : reviewItems.length > 0 ? (
          <div className="flex flex-col gap-0.5">
            {reviewItems.map((r) => <RecLine key={r.priority} rec={r} />)}
          </div>
        ) : (
          <p className="text-[12px] text-gray-400">No pending reviews.</p>
        )}
      </CompactSection>

      {/* ------------------------------------------------------------------ */}
      {/* Learning                                                             */}
      {/* ------------------------------------------------------------------ */}

      <CompactSection icon={<LearnIcon />} title="Learning" href={IBM_BOB_URL}>
        {recsAreLoading ? (
          <div className="py-0.5"><LoadingSpinner /></div>
        ) : learnItems.length > 0 ? (
          <div className="flex flex-col gap-0.5">
            {learnItems.map((r) => <RecLine key={r.priority} rec={r} />)}
          </div>
        ) : (
          <p className="text-[12px] text-gray-400">No learning items right now.</p>
        )}
      </CompactSection>

    </div>
  )
}
