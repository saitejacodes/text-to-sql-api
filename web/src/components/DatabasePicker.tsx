import type { DatabaseInfo } from '../types'

interface Props {
  databases: DatabaseInfo[]
  value: string
  onChange: (id: string) => void
  disabled?: boolean
}

export function DatabasePicker({ databases, value, onChange, disabled }: Props) {
  const selected = databases.find((d) => d.id === value)
  return (
    <div className="space-y-2">
      <label htmlFor="db" className="block text-sm font-medium text-slate-700 dark:text-slate-300">
        Database
      </label>
      <select
        id="db"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        {databases.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>
      {selected && (
        <details className="rounded-lg border border-slate-200 bg-slate-50 text-sm dark:border-slate-800 dark:bg-slate-900/60">
          <summary className="cursor-pointer select-none px-3 py-2 font-medium text-slate-700 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:text-slate-300">
            Schema · {selected.tables.length} tables
          </summary>
          <ul className="max-h-64 space-y-2 overflow-y-auto px-3 pb-3">
            {selected.tables.map((t) => (
              <li key={t.name}>
                <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">{t.name}</span>
                <span className="block break-words font-mono text-xs text-slate-500 dark:text-slate-400">
                  {t.columns.join(', ')}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
