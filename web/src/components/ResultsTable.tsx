import { downloadCsv } from '../lib/csv'
import type { Cell } from '../types'

interface Props {
  columns: string[]
  rows: Cell[][]
  truncated: boolean
}

function show(value: Cell): string {
  return value === null ? 'NULL' : String(value)
}

export function ResultsTable({ columns, rows, truncated }: Props) {
  return (
    <section aria-label="Results" className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {rows.length} {rows.length === 1 ? 'row' : 'rows'}
          {truncated && ' · showing the first rows only (result was truncated)'}
        </p>
        <button
          type="button"
          disabled={!rows.length}
          onClick={() => downloadCsv('asksql-results.csv', columns, rows)}
          className="rounded-lg border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Export CSV
        </button>
      </div>
      <div className="max-h-96 overflow-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="min-w-full text-left text-sm">
          <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
            <tr>
              {columns.map((c) => (
                <th key={c} scope="col" className="whitespace-nowrap px-3 py-2 font-semibold text-slate-800 dark:text-slate-200">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {rows.map((row, i) => (
              <tr key={i} className="odd:bg-white even:bg-slate-50 dark:odd:bg-slate-950 dark:even:bg-slate-900">
                {row.map((v, j) => (
                  <td
                    key={j}
                    className={`whitespace-nowrap px-3 py-1.5 ${v === null ? 'italic text-slate-400' : 'text-slate-700 dark:text-slate-300'}`}
                  >
                    {show(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <p className="px-3 py-4 text-sm text-slate-500 dark:text-slate-400">The query ran but returned no rows.</p>
        )}
      </div>
    </section>
  )
}
