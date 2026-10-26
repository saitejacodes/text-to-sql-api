import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { ConfidenceMeter } from '../components/ConfidenceMeter'
import { DatabasePicker } from '../components/DatabasePicker'
import { ErrorBanner } from '../components/ErrorBanner'
import { ExampleQuestions } from '../components/ExampleQuestions'
import { HistoryPanel } from '../components/HistoryPanel'
import { QueryBox } from '../components/QueryBox'
import { ResultSkeleton } from '../components/ResultSkeleton'
import { ResultsTable } from '../components/ResultsTable'
import { SafetyBadge } from '../components/SafetyBadge'
import { SqlViewer } from '../components/SqlViewer'
import { addToHistory, loadHistory } from '../lib/history'
import type { DatabaseInfo, HistoryItem, QueryResponse } from '../types'

export function Home() {
  const [databases, setDatabases] = useState<DatabaseInfo[]>([])
  const [dbId, setDbId] = useState('')
  const [examples, setExamples] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [history, setHistory] = useState<HistoryItem[]>(loadHistory)

  useEffect(() => {
    api
      .databases()
      .then((dbs) => {
        setDatabases(dbs)
        if (dbs.length) setDbId((current) => current || dbs[0].id)
      })
      .catch(setError)
  }, [])

  useEffect(() => {
    if (!dbId) return
    api
      .examples(dbId)
      .then((r) => setExamples(r.questions))
      .catch(() => setExamples([]))
  }, [dbId])

  async function ask(item: HistoryItem) {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.query(item))
      setHistory((h) => addToHistory(h, item))
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  function rerun(item: HistoryItem) {
    setDbId(item.db_id)
    setQuestion(item.question)
    void ask(item)
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="space-y-6">
        <DatabasePicker databases={databases} value={dbId} onChange={setDbId} disabled={loading} />
        <ExampleQuestions questions={examples} onPick={setQuestion} disabled={loading} />
        <QueryBox
          value={question}
          onChange={setQuestion}
          loading={loading}
          onSubmit={() => void ask({ db_id: dbId, question: question.trim() })}
        />
        <HistoryPanel items={history} onRerun={rerun} disabled={loading} />
      </div>

      <div className="min-w-0 space-y-4" aria-live="polite" aria-busy={loading}>
        {error !== null && <ErrorBanner error={error} onDismiss={() => setError(null)} />}
        {loading && <ResultSkeleton />}
        {!loading && !result && error === null && (
          <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-500 dark:border-slate-700 dark:text-slate-400">
            Pick a database and ask a question. The generated SQL and its results appear here.
          </p>
        )}
        {result && (
          <>
            <SafetyBadge status={result.status} reason={result.blocked_reason} />
            {result.status === 'error' && (
              <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-100 dark:ring-amber-900">
                Couldn&apos;t answer this one: {result.error}
              </p>
            )}
            {result.sql && <SqlViewer sql={result.sql} />}
            {result.status === 'ok' && (
              <>
                <ConfidenceMeter agreement={result.agreement} candidates={result.candidates_considered} />
                <ResultsTable columns={result.columns} rows={result.rows} truncated={result.truncated} />
              </>
            )}
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {(result.latency_ms / 1000).toFixed(1)} s · {result.model}
              {result.repaired && ' · repaired after an error'}
            </p>
          </>
        )}
      </div>
    </div>
  )
}
