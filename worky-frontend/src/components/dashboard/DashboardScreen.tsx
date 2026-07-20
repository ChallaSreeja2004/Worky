/**
 * src/components/dashboard/DashboardScreen.tsx
 * ==============================================
 * Main widget view shown after the user has authenticated.
 *
 * This component is presentation-only.  It receives pre-fetched data as
 * props from ScreenManager and renders it.  It never calls useOutlookContext
 * or any other hook directly — that is ScreenManager's responsibility.
 *
 * Section map
 * -----------
 * Upcoming Meetings  — live: data.calendar_events from ConnectorResult
 * Important Emails   — live: data.emails from ConnectorResult
 * Today's Priorities — future: IBM Bob recommendations (Phase 6+)
 * Blockers           — future: IBM Bob analysis (Phase 6+)
 * Learning Reminder  — future: IBM Bob recommendation (Phase 6+)
 *
 * Props
 * -----
 * result       — ConnectorResult from useOutlookContext, or null before first fetch
 * isLoading    — true while the first fetch is in flight (no data yet)
 * isRefreshing — true while a refresh is in flight (stale data still shown)
 * error        — network/unexpected error string, or null
 */

import type { ConnectorResult } from '../../types/index.ts'
import MeetingList from './MeetingList.tsx'
import EmailList from './EmailList.tsx'
import ErrorBanner from '../shared/ErrorBanner.tsx'
import StatusBadge from '../shared/StatusBadge.tsx'

interface DashboardScreenProps {
  result: ConnectorResult | null
  isLoading: boolean
  isRefreshing: boolean
  error: string | null
}

// ---------------------------------------------------------------------------
// Section wrapper — shared chrome for each data section
// ---------------------------------------------------------------------------

interface SectionProps {
  title: string
  children: React.ReactNode
  comingSoon?: boolean
}

function Section({ title, children, comingSoon = false }: SectionProps) {
  return (
    <section className="pt-3 pb-2">
      <div className="flex items-center justify-between px-4 mb-1.5">
        <p className="text-[11px] font-medium text-gray-400">{title}</p>
        {comingSoon && (
          <span className="text-[10px] text-gray-300">Coming soon</span>
        )}
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
}: DashboardScreenProps) {
  const events = result?.data?.calendar_events ?? []
  const emails = result?.data?.emails ?? []

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

      {/* Upcoming Meetings */}
      <Section title="upcoming meetings">
        <MeetingList events={events} isLoading={isLoading} />
      </Section>

      {/* Important Emails */}
      <Section title="important emails">
        <EmailList emails={emails} isLoading={isLoading} />
      </Section>

      {/* Future IBM Bob sections — placeholders */}
      <Section title="today's priorities" comingSoon>
        <p className="px-4 py-2 text-xs text-gray-300">Not yet connected.</p>
      </Section>

      <Section title="blockers" comingSoon>
        <p className="px-4 py-2 text-xs text-gray-300">Not yet connected.</p>
      </Section>

      <Section title="learning reminder" comingSoon>
        <p className="px-4 py-2 text-xs text-gray-300">Not yet connected.</p>
      </Section>

    </div>
  )
}
