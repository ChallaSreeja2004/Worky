/**
 * src/components/dashboard/EmailCard.tsx
 * ========================================
 * Single email row rendered inside EmailList.
 *
 * Display rules (from DESIGN.md)
 * ------------------------------
 *   • Subject: text-sm font-medium text-gray-800
 *   • Sender + timestamp: text-xs text-gray-500
 *   • Body preview: text-xs text-gray-400 — one line, truncated
 *   • Unread emails: subject in font-semibold (slightly bolder) with a
 *     small blue dot indicator on the left edge
 *   • High-importance emails: subject in text-gray-900 (stronger contrast)
 *   • Attachments: a small paperclip indicator in the subject row
 *   • No card shadows — row-level hover only (hover:bg-gray-50)
 */

import type { Email } from '../../types/index.ts'
import { formatEmailTime } from '../../utils/formatters.ts'

interface EmailCardProps {
  email: Email
}

export default function EmailCard({ email }: EmailCardProps) {
  const timeLabel  = formatEmailTime(email.received_at)
  const isUnread   = !email.is_read
  const isHighImportance = email.importance === 'high'

  return (
    <div className="flex gap-2.5 px-4 py-2 hover:bg-gray-50 transition-colors duration-100">

      {/* Unread indicator dot
        * C9: a bare aria-label on a <span> is not reliably announced by all
        * screen readers.  Use a visually-hidden text node inside the span so
        * the label is part of the accessibility tree as real text content. */}
      <div className="pt-1.5 shrink-0">
        {isUnread ? (
          <span className="block h-1.5 w-1.5 rounded-full bg-blue-500" aria-hidden="true">
            <span className="sr-only">Unread</span>
          </span>
        ) : (
          <span className="block h-1.5 w-1.5" aria-hidden="true" />
        )}
      </div>

      {/* Content */}
      <div className="flex flex-col gap-0.5 min-w-0">

        {/* Subject row */}
        <div className="flex items-center gap-1.5">
          <span
            className={`text-sm truncate ${
              isHighImportance
                ? 'font-semibold text-gray-900'
                : isUnread
                  ? 'font-semibold text-gray-800'
                  : 'font-medium text-gray-700'
            }`}
          >
            {email.subject || '(No subject)'}
          </span>

          {/* Attachment indicator
            * C9: SVGs used as images need role="img" so assistive technology
            * treats them as an image element and announces aria-label. */}
          {email.has_attachments && (
            <svg
              className="shrink-0 h-3 w-3 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              role="img"
              aria-label="Has attachments"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13"
              />
            </svg>
          )}
        </div>

        {/* Sender + time row */}
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <span className="truncate">{email.sender_name || email.sender_email || 'Unknown sender'}</span>
          <span className="text-gray-300 shrink-0" aria-hidden="true">·</span>
          <span className="shrink-0">{timeLabel}</span>
        </div>

        {/* Body preview */}
        {email.body_preview && (
          <p className="text-xs text-gray-400 truncate">{email.body_preview}</p>
        )}

      </div>
    </div>
  )
}
