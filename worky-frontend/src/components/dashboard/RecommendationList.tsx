/**
 * src/components/dashboard/RecommendationList.tsx
 * =================================================
 * Renders the compact "Today's Priorities" numbered list inside DashboardScreen.
 *
 * Shows the top 3 recommendations only.  If there are more than 3 the overflow
 * count is shown as "+N more" linking to IBM Bob.
 *
 * States
 * ------
 *   loading    — spinner + "Bob is analysing…" text (two lines)
 *   error      — compact inline error banner
 *   empty      — all caught up message
 *   populated  — top-3 PriorityRow items + optional overflow count
 */

import type { Recommendation } from '../../types/index.ts'
import LoadingSpinner from '../shared/LoadingSpinner.tsx'
import PriorityRow from './PriorityRow.tsx'

interface RecommendationListProps {
  items: Recommendation[]
  isLoading: boolean
  error: string | null
}

const IBM_BOB_URL = 'https://ibm.com/products/watsonx'

export default function RecommendationList({ items, isLoading, error }: RecommendationListProps) {
  if (isLoading) {
    return (
      <div className="flex flex-col items-center gap-2 py-4">
        <LoadingSpinner />
        <p className="text-xs text-gray-500 text-center max-w-[220px] leading-relaxed">
          IBM Bob is analysing your calendar and emails…
        </p>
        <p className="text-[11px] text-gray-400 text-center">
          This can take up to 30 seconds.
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-xs text-red-700">
        Could not load recommendations — try refreshing.
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg bg-gray-50 border border-gray-100 px-3 py-2.5 text-center">
        <p className="text-xs text-gray-500">You're all caught up 🎉</p>
      </div>
    )
  }

  const top3    = items.slice(0, 3)
  const overflow = items.length - 3

  return (
    <div className="flex flex-col gap-0">
      {top3.map((item, index) => (
        <PriorityRow key={item.priority} item={item} rank={index + 1} />
      ))}

      {overflow > 0 && (
        <a
          href={IBM_BOB_URL}
          target="_blank"
          rel="noreferrer"
          className="mt-1 text-[11px] text-blue-600 hover:text-blue-700 font-medium"
        >
          +{overflow} more — View in IBM Bob
        </a>
      )}
    </div>
  )
}
