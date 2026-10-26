// Mirrors the Pydantic models in src/t2sql/api/web.py. Keep the two in sync.

export interface TableInfo {
  name: string
  columns: string[]
}

export interface DatabaseInfo {
  id: string
  name: string
  tables: TableInfo[]
}

export interface ExamplesResponse {
  db_id: string
  questions: string[]
}

export interface QueryRequest {
  db_id: string
  question: string
}

export type QueryStatus = 'ok' | 'blocked' | 'error'

export type Cell = string | number | boolean | null

export interface QueryResponse {
  request_id: string
  status: QueryStatus
  sql: string
  columns: string[]
  rows: Cell[][]
  row_count: number
  truncated: boolean
  blocked_reason: string | null
  error: string | null
  agreement: number
  candidates_considered: number
  repaired: boolean
  latency_ms: number
  model: string
}

export interface HistoryItem {
  db_id: string
  question: string
}
