interface Props {
  questions: string[]
  onPick: (question: string) => void
  disabled?: boolean
}

export function ExampleQuestions({ questions, onPick, disabled }: Props) {
  if (!questions.length) return null
  return (
    <div>
      <h2 className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-300">Try an example</h2>
      <ul className="flex flex-wrap gap-2">
        {questions.map((q) => (
          <li key={q}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(q)}
              className="rounded-full border border-slate-300 bg-white px-3 py-1 text-left text-sm text-slate-700 hover:border-indigo-400 hover:text-indigo-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-indigo-300"
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
