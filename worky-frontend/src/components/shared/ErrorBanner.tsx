/**
 * src/components/shared/ErrorBanner.tsx
 * =======================================
 * Reusable error message banner.
 *
 * Displayed when an API call fails or when the connector returns a FAILED
 * or PARTIAL status.  Phase 3 will use this inside the dashboard sections.
 *
 * Props
 * -----
 * message  — human-readable error description shown to the user
 */

interface ErrorBannerProps {
  message: string
}

export default function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div
      className="rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700"
      role="alert"
    >
      {message}
    </div>
  )
}
