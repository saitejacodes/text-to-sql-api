import type { HistoryItem } from '../types'

interface Props {
  items: HistoryItem[]
  onRerun: (item: HistoryItem) => void
  disabled?: boolean
}

export function HistoryPanel({ items, onRerun, disabled }: Props) {
  return (
    <section aria-labelledby="history-title">
      <h2 id="history-title" className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-300">
        Recent questions
      </h2>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Your last 10 questions in this tab show up here.</p>
      ) : (
        <ul className="space-y-1">
          {items.map((h) => (
            <li key={`${h.db_id}:${h.question}`}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onRerun(h)}
                className="w-full truncate rounded px-2 py-1 text-left text-sm text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50 dark:text-slate-300 dark:hover:bg-slate-800"
                title={h.question}
              >
                {h.question}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
