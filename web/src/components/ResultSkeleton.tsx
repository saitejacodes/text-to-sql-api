export function ResultSkeleton() {
  return (
    <div aria-hidden="true" className="animate-pulse space-y-3">
      <div className="h-7 w-48 rounded-lg bg-slate-200 dark:bg-slate-800" />
      <div className="h-24 rounded-lg bg-slate-200 dark:bg-slate-800" />
      <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-800" />
      <div className="space-y-1.5">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-6 rounded bg-slate-200 dark:bg-slate-800" />
        ))}
      </div>
    </div>
  )
}
