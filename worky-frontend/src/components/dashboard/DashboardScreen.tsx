/**
 * src/components/dashboard/DashboardScreen.tsx
 * ==============================================
 * Main widget view shown after the user has authenticated.
 *
 * This component is presentation-only.  It receives pre-fetched data as
 * props from ScreenManager and renders it.  It never calls hooks directly —
 * that is ScreenManager's responsibility.
 *
 * Section map
 * -----------
 * Today's Priorities  — live: IBM Bob recommendations from RecommendationSet
 * Upcoming Meetings   — live: data.calendar_events from ConnectorResult
 * Important Emails    — live: data.emails from ConnectorResult
 *
 * Props
 * -----
 * result           — ConnectorResult from useOutlookContext, or null before first fetch
 * isLoading        — true while the first Outlook fetch is in flight (no data yet)
 * isRefreshing     — true while a refresh is in flight (stale data still shown)
 * error            — Outlook network/unexpected error string, or null
 * recommendations  — Recommendation[] from useRecommendations, or null before first fetch
 * recsLoading      — true while recommendations are being fetched for the first time
 * recsError        — recommendations error string, or null
 */

import type { ConnectorResult, Recommendation } from '../../types/index.ts'
import MeetingList from './MeetingList.tsx'
import EmailList from './EmailList.tsx'
import RecommendationList from './RecommendationList.tsx'
import ErrorBanner from '../shared/ErrorBanner.tsx'
import StatusBadge from '../shared/StatusBadge.tsx'

interface DashboardScreenProps {
  result: ConnectorResult | null
  isLoading: boolean
  isRefreshing: boolean
  error: string | null
  recommendations: Recommendation[] | null
  recsLoading: boolean
  recsError: string | null
}

// ---------------------------------------------------------------------------
// Section wrapper — shared chrome for each data section
// ---------------------------------------------------------------------------

interface SectionProps {
  title: string
  children: React.ReactNode
}

function Section({ title, children }: SectionProps) {
  return (
    <section className="pt-3 pb-2">
      <div className="flex items-center justify-between px-4 mb-1.5">
        <p className="text-[11px] font-medium text-gray-400">{title}</p>
      </div>
      <div className="border-b border-gray-50">
        {children}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// DashboardScreen
// ---------------------------------------------------------------------------

export default function DashboardScreen({
  result,
  isLoading,
  isRefreshing,
  error,
  recommendations,
  recsLoading,
  recsError,
}: DashboardScreenProps) {
  const events = result?.data?.calendar_events ?? []
  const emails = result?.data?.emails ?? []

  // Recommendations are shown in the order Bob provides (priority ascending).
  // Null before first fetch is treated the same as loading.
  const recItems = recommendations ?? []
  const recsAreLoading = recsLoading || (recommendations === null && !recsError)

  return (
    <div className="flex flex-col py-1">

      {/* Network or unexpected error banner — shown above all sections */}
      {error && !isLoading && (
        <div className="px-4 pt-3 pb-1">
          <ErrorBanner message="Could not load Outlook data. Check your connection and try refreshing." />
        </div>
      )}

      {/* Connector partial/failed status banner */}
      {result && result.status !== 'success' && (
        <div className="px-4 pt-2 pb-1 flex items-center gap-2">
          <StatusBadge status={result.status} />
          {result.errors.length > 0 && (
            <span className="text-xs text-gray-500 truncate">{result.errors[0]}</span>
          )}
        </div>
      )}

      {/* Refreshing indicator — subtle, non-disruptive */}
      {isRefreshing && (
        <div className="px-4 pt-1 pb-0">
          <p className="text-[10px] text-gray-400">Refreshing…</p>
        </div>
      )}

      {/* Today's Priorities — IBM Bob recommendations */}
      <Section title="today's priorities">
        <RecommendationList
          items={recItems}
          isLoading={recsAreLoading}
          error={recsError}
        />
      </Section>

      {/* Upcoming Meetings */}
      <Section title="upcoming meetings">
        <MeetingList events={events} isLoading={isLoading} />
      </Section>

      {/* Important Emails */}
      <Section title="important emails">
        <EmailList emails={emails} isLoading={isLoading} />
      </Section>

    </div>
  )
}
