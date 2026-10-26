import type { QueryStatus } from '../types'

interface Props {
  status: QueryStatus
  reason: string | null
}

export function SafetyBadge({ status, reason }: Props) {
  if (status === 'blocked') {
    return (
      <p
        role="status"
        className="inline-flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-800 ring-1 ring-rose-200 dark:bg-rose-950/50 dark:text-rose-200 dark:ring-rose-900"
      >
        <span aria-hidden="true">⛔</span>
        <span>Blocked: {reason ?? 'refused by the security sandbox'}</span>
      </p>
    )
  }
  if (status === 'ok') {
    return (
      <p
        role="status"
        className="inline-flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800 ring-1 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-200 dark:ring-emerald-900"
      >
        <span aria-hidden="true">✓</span>
        Passed security sandbox
      </p>
    )
  }
  return null
}
