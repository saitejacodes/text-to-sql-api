import type { HistoryItem } from '../types'

const KEY = 'asksql.history'
const MAX = 10

// sessionStorage can be missing or throw (private mode, blocked storage); history is a
// convenience, so failures just mean an empty list.
export function loadHistory(): HistoryItem[] {
  try {
    const raw = sessionStorage.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? (parsed as HistoryItem[]).slice(0, MAX) : []
  } catch {
    return []
  }
}

export function addToHistory(items: HistoryItem[], item: HistoryItem): HistoryItem[] {
  const next = [item, ...items.filter((h) => !(h.db_id === item.db_id && h.question === item.question))]
  const trimmed = next.slice(0, MAX)
  try {
    sessionStorage.setItem(KEY, JSON.stringify(trimmed))
  } catch {
    // ignore
  }
  return trimmed
}
