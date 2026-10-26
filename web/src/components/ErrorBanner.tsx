import { ApiError } from '../api/client'

function friendlyMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.kind) {
      case 'network':
        return 'Could not reach the server. Check your connection, or the demo may be restarting. Try again in a moment.'
      case 'rate_limit':
        return 'You are asking very fast. The demo allows a few questions per minute, so please wait a minute and try again.'
      case 'not_found':
        return 'That database is not available.'
      case 'validation':
        return 'Please check your question: it must be 3–500 characters.'
      case 'server':
        return 'The server had a problem answering. Please try again.'
    }
  }
  return 'Something went wrong. Please try again.'
}

interface Props {
  error: unknown
  onDismiss?: () => void
}

export function ErrorBanner({ error, onDismiss }: Props) {
  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-3 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-900 ring-1 ring-rose-200 dark:bg-rose-950/50 dark:text-rose-100 dark:ring-rose-900"
    >
      <p>{friendlyMessage(error)}</p>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="rounded px-1 text-rose-700 hover:bg-rose-100 focus-visible:outline-2 focus-visible:outline-rose-500 dark:text-rose-200 dark:hover:bg-rose-900"
        >
          ✕
        </button>
      )}
    </div>
  )
}
