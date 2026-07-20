/**
 * src/components/dashboard/DashboardScreen.tsx
 * ==============================================
 * Main widget view shown after the user has authenticated.
 *
 * Currently renders placeholder sections only — no data is fetched.
 * Phase 3 will replace each active section with live data from the
 * Outlook context endpoint (GET /api/v1/connectors/outlook/context).
 *
 * Section map
 * -----------
 * Upcoming Meetings  — Phase 3: data.calendar_events from ConnectorResult
 * Important Emails   — Phase 3: data.emails from ConnectorResult
 * Today's Priorities — future: IBM Bob recommendations (Phase 9+)
 * Blockers           — future: IBM Bob analysis (Phase 9+)
 * Learning Reminder  — future: IBM Bob recommendation (Phase 9+)
 */

import LoadingSpinner from '../shared/LoadingSpinner.tsx'

interface PlaceholderSectionProps {
  title: string
  comingSoon?: boolean
}

function PlaceholderSection({ title, comingSoon = false }: PlaceholderSectionProps) {
  return (
    <section className="px-4 pt-3 pb-2">
      <div className="flex items-center justify-between mb-1.5">
        <h3 className="text-[11px] font-medium text-gray-400">
          {title}
        </h3>
        {comingSoon && (
          <span className="text-[10px] text-gray-300">Coming soon</span>
        )}
      </div>

      <div className="border-b border-gray-50 pb-2">
        {comingSoon ? (
          <p className="text-xs text-gray-300">Not yet connected.</p>
        ) : (
          <LoadingSpinner />
        )}
      </div>
    </section>
  )
}

export default function DashboardScreen() {
  return (
    <div className="flex flex-col py-1">

      {/* Active in Phase 3 — will show live calendar events */}
      <PlaceholderSection title="Upcoming Meetings" />

      {/* Active in Phase 3 — will show live email data */}
      <PlaceholderSection title="Important Emails" />

      {/* Future phases — IBM Bob powered */}
      <PlaceholderSection title="Today's Priorities" comingSoon />
      <PlaceholderSection title="Blockers"           comingSoon />
      <PlaceholderSection title="Learning Reminder"  comingSoon />

    </div>
  )
}
