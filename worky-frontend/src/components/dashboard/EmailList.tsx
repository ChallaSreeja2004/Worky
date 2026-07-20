/**
 * src/components/dashboard/EmailList.tsx
 * ========================================
 * Emails section rendered inside DashboardScreen.
 *
 * Handles three states:
 *   loading    — shows LoadingSpinner while first fetch is in flight
 *   empty      — shows a calm "No important emails" message
 *   populated  — renders one EmailCard per email message
 */

import type { Email } from '../../types/index.ts'
import LoadingSpinner from '../shared/LoadingSpinner.tsx'
import EmailCard from './EmailCard.tsx'

interface EmailListProps {
  emails: Email[]
  isLoading: boolean
}

export default function EmailList({ emails, isLoading }: EmailListProps) {
  if (isLoading) {
    return (
      <div className="px-4 py-3">
        <LoadingSpinner />
      </div>
    )
  }

  if (emails.length === 0) {
    return (
      <p className="px-4 py-2 text-xs text-gray-400">No important emails.</p>
    )
  }

  return (
    <div className="flex flex-col">
      {emails.map((email) => (
        <EmailCard key={email.id} email={email} />
      ))}
    </div>
  )
}
