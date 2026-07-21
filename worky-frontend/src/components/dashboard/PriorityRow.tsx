/**
 * src/components/dashboard/PriorityRow.tsx
 * ==========================================
 * A single compact numbered row in the "Today's Priorities" list.
 *
 * Design intent
 * -------------
 * One row = one line of vertical space (~28 px).  The priority number sits in
 * a small coloured badge on the left.  The title is the primary (and only)
 * visible text.  An "Open →" link appears when a deep-link URL is available.
 *
 * Description is intentionally omitted from the row to keep the widget compact.
 * IBM Bob's full reasoning is accessible via "View in IBM Bob" in the footer.
 *
 * This replaces the previous large tinted card that caused excessive scrolling.
 *
 * NOTE: The heuristic categorisation helpers (blockers / pendingReviews /
 * learningItems) that assign recommendations to sections live in DashboardScreen.
 * They are the only place to update when the backend adds structured metadata.
 */

import type { Recommendation } from '../../types/index.ts'

interface PriorityRowProps {
  item: Recommendation
  /** 1-based display rank (may differ from item.priority after slicing top-3) */
  rank: number
}

// Number badge colour by display rank
function badgeClass(rank: number): string {
  if (rank === 1) return 'bg-red-500 text-white'
  if (rank === 2) return 'bg-orange-400 text-white'
  return 'bg-blue-500 text-white'
}

export default function PriorityRow({ item, rank }: PriorityRowProps) {
  return (
    <div className="flex items-center gap-2.5 py-1 hover:bg-gray-50 rounded transition-colors duration-100">

      {/* Numbered badge */}
      <span
        className={`shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-md text-[11px] font-bold ${badgeClass(rank)}`}
        aria-label={`Priority ${rank}`}
      >
        {rank}
      </span>

      {/* Title + optional open link — single line */}
      <div className="flex items-baseline justify-between gap-2 min-w-0 flex-1">
        <span className="text-[12px] font-semibold text-gray-900 leading-snug truncate">
          {item.title}
        </span>
        {item.action_url && (
          <a
            href={item.action_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-[11px] font-medium text-blue-600 hover:text-blue-700"
          >
            Open →
          </a>
        )}
      </div>

    </div>
  )
}
