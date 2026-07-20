/**
 * src/components/shared/LoadingSpinner.tsx
 * =========================================
 * Compact inline loading indicator.
 *
 * Used during API fetches when data is not yet available.
 * Phase 3 will render this inside dashboard sections while
 * the Outlook context is being fetched.
 */

export default function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-3">
      <div
        className="h-4 w-4 animate-spin rounded-full border-2 border-gray-200 border-t-blue-500"
        role="status"
        aria-label="Loading"
      />
    </div>
  )
}
