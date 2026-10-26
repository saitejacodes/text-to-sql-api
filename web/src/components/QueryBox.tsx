import type { FormEvent, KeyboardEvent } from 'react'

const MAX_QUESTION = 500

interface Props {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  loading: boolean
}

export function QueryBox({ value, onChange, onSubmit, loading }: Props) {
  const tooShort = value.trim().length < 3
  const canSubmit = !loading && !tooShort && value.length <= MAX_QUESTION

  function submit(e?: FormEvent) {
    e?.preventDefault()
    if (canSubmit) onSubmit()
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit()
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <label htmlFor="question" className="block text-sm font-medium text-slate-700 dark:text-slate-300">
        Your question
      </label>
      <textarea
        id="question"
        rows={3}
        maxLength={MAX_QUESTION}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="e.g. Which instructors teach in the Stata Center?"
        aria-describedby="question-hint"
        className="w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      <div className="flex items-center justify-between gap-3">
        <p id="question-hint" className="text-xs text-slate-500 dark:text-slate-400">
          {value.length}/{MAX_QUESTION} · Ctrl/⌘ + Enter to ask
        </p>
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-lg bg-indigo-600 px-5 py-2 font-medium text-white hover:bg-indigo-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-400 dark:disabled:bg-slate-700"
        >
          {loading ? 'Thinking…' : 'Ask'}
        </button>
      </div>
    </form>
  )
}
