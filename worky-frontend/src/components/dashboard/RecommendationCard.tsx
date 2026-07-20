/**
 * src/components/dashboard/RecommendationCard.tsx
 * =================================================
 * Single IBM Bob recommendation row rendered inside RecommendationList.
 *
 * Display rules (from DESIGN.md)
 * ------------------------------
 *   • Priority number: small muted badge on the left edge
 *   • Title: text-sm font-medium text-gray-800 — the primary read target
 *   • Description: text-xs text-gray-400 — one line, truncated
 *   • Source label: text-[10px] text-gray-300 (muted, not prominent)
 *   • Action link: "Open" when action_url is present — small blue link
 *   • Category icon: subtle SVG in the priority badge area to signal type
 *   • No card shadows — row-level hover only (hover:bg-gray-50)
 */

import type { Recommendation } from '../../types/index.ts'

interface RecommendationCardProps {
  item: Recommendation
}

// Maps category to a compact label shown alongside the priority number.
const CATEGORY_LABELS: Record<string, string> = {
  email:   'Email',
  meeting: 'Meeting',
  message: 'Message',
  task:    'Task',
  general: 'General',
}

export default function RecommendationCard({ item }: RecommendationCardProps) {
  const categoryLabel = CATEGORY_LABELS[item.category] ?? item.category

  return (
    <div className="flex gap-3 px-4 py-2 hover:bg-gray-50 transition-colors duration-100">

      {/* Priority badge */}
      <div className="shrink-0 flex items-start pt-0.5">
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-blue-50 text-[10px] font-semibold text-blue-600">
          {item.priority}
        </span>
      </div>

      {/* Content */}
      <div className="flex flex-col gap-0.5 min-w-0 flex-1">

        {/* Title row */}
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-medium text-gray-800 leading-snug">
            {item.title}
          </span>

          {/* Open link — only shown when a deep-link URL is available */}
          {item.action_url && (
            <a
              href={item.action_url}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 text-[11px] font-medium text-blue-600 hover:text-blue-700"
            >
              Open
            </a>
          )}
        </div>

        {/* Description */}
        {item.description && (
          <p className="text-xs text-gray-400 line-clamp-2 leading-relaxed">
            {item.description}
          </p>
        )}

        {/* Source + category footer */}
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="text-[10px] text-gray-300">{item.source}</span>
          <span className="text-gray-200 shrink-0" aria-hidden="true">·</span>
          <span className="text-[10px] text-gray-300">{categoryLabel}</span>
        </div>

      </div>
    </div>
  )
}
