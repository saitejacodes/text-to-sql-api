// Numbers are copied from the repository README / runs/REPORT.md. Change them only there first.
const RESULTS = [
  ['Baseline: plain schema, one greedy answer', '45.6', '41.4–49.8'],
  ['+ column descriptions & example values (M-Schema)', '49.2', '44.8–53.6'],
  ['+ database-value retrieval', '48.8', '44.4–52.8'],
  ['+ 3 few-shot examples from the train split', '50.4', '45.8–54.6'],
  ['+ execution-feedback repair', '53.8', '49.2–58.0'],
  ['+ 5-way vote on execution results (full system)', '58.4', '53.8–62.7'],
]

const STEPS = [
  'Browser (React + TypeScript + Tailwind)',
  'FastAPI backend (Docker, rate-limited)',
  'Schema + value retrieval builds the prompt',
  'LLM writes 5 candidate queries',
  'Each candidate: AST guard → read-only sandbox → repair on error',
  'Vote: candidates returning the same rows agree',
  'SQLite (read-only) → rows + agreement back to the browser',
]

export function About() {
  return (
    <article className="max-w-3xl space-y-8 text-slate-700 dark:text-slate-300">
      <section className="space-y-2">
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">About AskSQL</h1>
        <p>
          AskSQL turns a plain-English question into a SQLite query and runs it. The model writes five
          candidate queries, fixes the ones that fail, and the answer most candidates agree on wins. Every
          query is treated as untrusted code and passes two independent security layers before it touches the
          database.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Benchmark results</h2>
        <p className="text-sm">
          BIRD mini-dev (SQLite), 498 scored questions over 11 databases, local 7B model{' '}
          <code className="font-mono">qwen2.5-coder:7b</code>. Each row adds one idea. 95% confidence intervals by
          bootstrap.
        </p>
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-100 dark:bg-slate-800">
              <tr>
                <th scope="col" className="px-3 py-2">Configuration</th>
                <th scope="col" className="px-3 py-2">Execution accuracy</th>
                <th scope="col" className="px-3 py-2">95% CI</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {RESULTS.map(([name, ex, ci], i) => (
                <tr key={name} className={i === RESULTS.length - 1 ? 'font-semibold' : ''}>
                  <td className="px-3 py-1.5">{name}</td>
                  <td className="px-3 py-1.5">{ex}%</td>
                  <td className="whitespace-nowrap px-3 py-1.5">{ci}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>+12.8 points end to end on a free laptop model.</li>
          <li>
            Agreement is a usable confidence signal: when all 5 candidates agree the answer is right 79.6% of the
            time; when 2 or fewer agree, 28.0%.
          </li>
          <li>Security: 14 of 14 red-team attacks blocked, and the database file is unchanged after each one.</li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">How it works</h2>
        <ol className="space-y-2">
          {STEPS.map((step, i) => (
            <li key={step} className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white">
                {i + 1}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="space-y-2 rounded-lg bg-slate-100 p-4 text-sm dark:bg-slate-900">
        <h2 className="font-semibold text-slate-900 dark:text-slate-100">A note on the live demo</h2>
        <p>
          The benchmark numbers above were measured on a local 7B model through Ollama. This hosted demo uses a
          hosted model (shown under each answer) to keep it free to run, so its accuracy may differ.
        </p>
      </section>
    </article>
  )
}
