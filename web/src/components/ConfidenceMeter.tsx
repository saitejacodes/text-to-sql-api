interface Props {
  agreement: number
  candidates: number
}

const LOW_AGREEMENT = 0.6

export function ConfidenceMeter({ agreement, candidates }: Props) {
  const agreed = Math.round(agreement * candidates)
  const low = agreement < LOW_AGREEMENT
  const pct = Math.round(agreement * 100)
  return (
    <section aria-label="Confidence" className="space-y-1.5">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium text-slate-700 dark:text-slate-300">
          {agreed} of {candidates} candidates agreed
        </span>
        <span className="text-slate-500 dark:text-slate-400">{pct}%</span>
      </div>
      <div
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label="Candidate agreement"
        className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
      >
        <div
          className={`h-full rounded-full ${low ? 'bg-amber-500' : 'bg-emerald-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        The model writes {candidates} different queries and runs each one. Queries that return the
        same rows agree. On the benchmark, answers where all 5 agreed were right 79.6% of the time.
      </p>
      {low && (
        <p className="rounded-md bg-amber-50 px-2 py-1 text-sm text-amber-900 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900">
          Low agreement, double-check this result.
        </p>
      )}
    </section>
  )
}
