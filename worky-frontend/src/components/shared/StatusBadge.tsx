/**
 * src/components/shared/StatusBadge.tsx
 * =======================================
 * Connector status indicator badge.
 *
 * Displays the ConnectorResult.status value returned by the backend.
 * Phase 3 will render this inside the dashboard header to show whether
 * the last Outlook context fetch was SUCCESS, PARTIAL, or FAILED.
 *
 * Props
 * -----
 * status  — one of: 'success' | 'partial' | 'failed'
 */

type ConnectorStatus = 'success' | 'partial' | 'failed'

interface StatusBadgeProps {
  status: ConnectorStatus
}

const STATUS_STYLES: Record<ConnectorStatus, string> = {
  success: 'bg-green-100 text-green-800',
  partial: 'bg-yellow-100 text-yellow-800',
  failed:  'bg-red-100 text-red-800',
}

const STATUS_LABELS: Record<ConnectorStatus, string> = {
  success: 'Up to date',
  partial: 'Partial data',
  failed:  'Unavailable',
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}
