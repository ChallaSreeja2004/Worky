/**
 * src/components/dashboard/RecommendationCard.tsx
 * =================================================
 * A visually dominant IBM Bob recommendation card.
 *
 * Design intent
 * -------------
 * This is the HERO component of the widget.  It must immediately communicate
 * "what to do next" and feel like an AI assistant card, not a list row.
 *
 *   • Coloured left-accent bar signals urgency via priority (1 = red, 2 = orange, …)
 *   • Category icon gives at-a-glance context (email, meeting, task, …)
 *   • Title is the primary read target — large, bold, high contrast
 *   • Description is secondary — limited to two lines
 *   • "Open" CTA appears when a deep-link URL is available
 *   • Source + category footer is minimal — not the primary focus
 */

import type { Recommendation } from '../../types/index.ts'

interface RecommendationCardProps {
  item: Recommendation
}

// Accent colour per priority rank (1 = highest urgency → red)
function accentClass(priority: number): string {
  if (priority === 1) return 'bg-red-500'
  if (priority === 2) return 'bg-orange-400'
  if (priority === 3) return 'bg-amber-400'
  return 'bg-blue-400'
}

// Background tint per priority rank
function bgClass(priority: number): string {
  if (priority === 1) return 'bg-red-50 hover:bg-red-50/80'
  if (priority === 2) return 'bg-orange-50 hover:bg-orange-50/80'
  if (priority === 3) return 'bg-amber-50 hover:bg-amber-50/80'
  return 'bg-blue-50 hover:bg-blue-50/80'
}

// Explicit priority label so urgency is unambiguous without reading colour
function priorityLabel(priority: number): { text: string; cls: string } {
  if (priority === 1) return { text: 'HIGH',   cls: 'bg-red-100 text-red-700 border-red-200' }
  if (priority === 2) return { text: 'HIGH',   cls: 'bg-red-100 text-red-700 border-red-200' }
  if (priority === 3) return { text: 'MED',    cls: 'bg-amber-100 text-amber-700 border-amber-200' }
  return                      { text: 'LOW',   cls: 'bg-blue-50 text-blue-600 border-blue-200' }
}

// Category icon — inline SVG paths (all viewBox 0 0 24 24, strokeWidth 1.5)
function CategoryIcon({ category }: { category: string }) {
  const cls = 'h-3.5 w-3.5 shrink-0 text-gray-500'
  if (category === 'email') {
    return (
      <svg className={cls} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 0 1-2.25 2.25h-15a2.25 2.25 0 0 1-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0 0 19.5 4.5h-15a2.25 2.25 0 0 0-2.25 2.25m19.5 0v.243a2.25 2.25 0 0 1-1.07 1.916l-7.5 4.615a2.25 2.25 0 0 1-2.36 0L3.32 8.91a2.25 2.25 0 0 1-1.07-1.916V6.75" />
      </svg>
    )
  }
  if (category === 'meeting') {
    return (
      <svg className={cls} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
      </svg>
    )
  }
  if (category === 'task') {
    return (
      <svg className={cls} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
      </svg>
    )
  }
  if (category === 'message') {
    return (
      <svg className={cls} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
      </svg>
    )
  }
  // general / fallback
  return (
    <svg className={cls} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
    </svg>
  )
}

export default function RecommendationCard({ item }: RecommendationCardProps) {
  return (
    <div className={`flex gap-0 rounded-lg mb-2 overflow-hidden border border-black/5 transition-opacity duration-100 ${bgClass(item.priority)}`}>
      {/* Left accent bar — colour signals priority level */}
      <div className={`w-1 shrink-0 ${accentClass(item.priority)}`} />

      <div className="flex flex-col gap-1 px-3 py-2.5 flex-1 min-w-0">
        {/* Title row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0 flex-1">
            <CategoryIcon category={item.category} />
            <span className="text-[13px] font-semibold text-gray-900 leading-snug">
              {item.title}
            </span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Explicit priority label — unambiguous without reading colour */}
            {(() => {
              const { text, cls } = priorityLabel(item.priority)
              return (
                <span className={`inline-flex items-center rounded border px-1.5 py-0 text-[9px] font-bold tracking-wider ${cls}`}>
                  {text}
                </span>
              )
            })()}
            {item.action_url && (
              <a
                href={item.action_url}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] font-semibold text-blue-600 hover:text-blue-700 bg-white/70 rounded px-1.5 py-0.5 border border-blue-200"
              >
                Open →
              </a>
            )}
          </div>
        </div>

        {/* Bob's reasoning — makes the AI nature of the description explicit */}
        {item.description && (
          <div className="flex gap-1 mt-0.5">
            <span className="shrink-0 text-[10px] font-semibold text-gray-400 mt-0.5 leading-tight">Bob:</span>
            <p className="text-[11px] text-gray-600 line-clamp-2 leading-relaxed">
              {item.description}
            </p>
          </div>
        )}

        {/* Footer: source tag */}
        <div className="flex items-center gap-1 mt-0.5">
          <span className="text-[10px] text-gray-400 capitalize">{item.source}</span>
          <span className="text-gray-300 mx-0.5" aria-hidden="true">·</span>
          <span className="text-[10px] text-gray-400 capitalize">{item.category}</span>
        </div>
      </div>
    </div>
  )
}
