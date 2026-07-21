/**
 * src/components/shared/DemoBadge.tsx
 * =====================================
 * Compact indicator shown in the widget header when Demo Mode is active.
 *
 * Only rendered when the authenticated user has is_demo === true.
 * Never rendered in production (real OAuth) sessions.
 *
 * Design rules (DESIGN.md)
 * ------------------------
 *   • Uses amber tones — same semantic colour as "partial / degraded" status.
 *   • Small pill shape (rounded-full) — consistent with StatusBadge.
 *   • No shadows, no animation, no decorative colour fills.
 *   • Tooltip explains the indicator without a separate modal.
 */

export default function DemoBadge() {
  return (
    <span
      className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700"
      title="Demo Mode — using representative Outlook data. No real Microsoft account connected."
    >
      Demo
    </span>
  )
}
