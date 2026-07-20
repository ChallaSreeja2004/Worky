/**
 * src/components/dashboard/RecommendationList.tsx
 * =================================================
 * IBM Bob recommendations section rendered inside DashboardScreen.
 *
 * Handles four states:
 *   loading    — shows LoadingSpinner while first fetch is in flight
 *   error      — shows ErrorBanner with a user-friendly message
 *   empty      — shows a calm "No recommendations right now" message
 *   populated  — renders one RecommendationCard per recommendation
 *
 * The recommendations are already sorted by priority ascending (1 first)
 * by the backend.  This component renders them in the order received.
 *
 * NOTE: Generating recommendations requires IBM Bob to process the Outlook
 * context.  On first load this can take 15–30 s.  The loading state is
 * intentionally patient — it shows a spinner and a brief explanatory note
 * rather than an error after a few seconds.
 */

import type { Recommendation } from '../../types/index.ts'
import LoadingSpinner from '../shared/LoadingSpinner.tsx'
import ErrorBanner from '../shared/ErrorBanner.tsx'
import RecommendationCard from './RecommendationCard.tsx'

interface RecommendationListProps {
  items: Recommendation[]
  isLoading: boolean
  error: string | null
}

export default function RecommendationList({ items, isLoading, error }: RecommendationListProps) {
  if (isLoading) {
    return (
      <div className="px-4 py-3 flex flex-col gap-2">
        <LoadingSpinner />
        <p className="text-[10px] text-gray-300 text-center">
          Bob is analysing your day…
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="px-4 py-2">
        <ErrorBanner message="Could not load recommendations. Try refreshing." />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <p className="px-4 py-2 text-xs text-gray-400">No recommendations right now.</p>
    )
  }

  return (
    <div className="flex flex-col">
      {items.map((item, index) => (
        <RecommendationCard key={index} item={item} />
      ))}
    </div>
  )
}
