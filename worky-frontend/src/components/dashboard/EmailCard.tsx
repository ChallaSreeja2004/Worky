/**
 * src/components/dashboard/EmailCard.tsx
 * ========================================
 * Compact email row for the supporting "Important Emails" section.
 *
 * In the new layout emails are supporting context, not the hero.
 * The card is deliberately compact — one line for subject, one for sender.
 * Unread and high-importance signals are preserved via dot indicator and weight.
 */

import type { Email } from '../../types/index.ts'
import { formatEmailTime } from '../../utils/formatters.ts'

interface EmailCardProps {
  email: Email
}

export default function EmailCard({ email }: EmailCardProps) {
  const timeLabel         = formatEmailTime(email.received_at)
  const isUnread          = !email.is_read
  const isHighImportance  = email.importance === 'high'

  return (
    <div className="flex items-start gap-2 px-3 py-2 hover:bg-gray-50 transition-colors duration-100">

      {/* Unread / importance indicator */}
      <div className="pt-1.5 shrink-0 flex flex-col items-center gap-0.5">
        {isUnread && (
          <span className="block h-1.5 w-1.5 rounded-full bg-blue-500" aria-hidden="true">
            <span className="sr-only">Unread</span>
          </span>
        )}
        {!isUnread && <span className="block h-1.5 w-1.5" aria-hidden="true" />}
        {isHighImportance && (
          <span className="block h-1 w-1 rounded-full bg-red-400 mt-0.5" aria-hidden="true">
            <span className="sr-only">High importance</span>
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex flex-col gap-0.5 min-w-0 flex-1">
        <span
          className={`text-xs truncate ${
            isHighImportance
              ? 'font-semibold text-gray-900'
              : isUnread
                ? 'font-semibold text-gray-800'
                : 'font-medium text-gray-600'
          }`}
        >
          {email.subject || '(No subject)'}
        </span>

        <div className="flex items-center gap-1.5 text-[11px] text-gray-400">
          <span className="truncate">{email.sender_name || email.sender_email || 'Unknown'}</span>
          <span className="text-gray-300 shrink-0" aria-hidden="true">·</span>
          <span className="shrink-0">{timeLabel}</span>
          {email.has_attachments && (
            <span className="shrink-0 text-gray-300" aria-label="Has attachments">📎</span>
          )}
        </div>

      </div>
    </div>
  )
}
