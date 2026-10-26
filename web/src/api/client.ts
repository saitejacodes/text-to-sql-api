import type { DatabaseInfo, ExamplesResponse, QueryRequest, QueryResponse } from '../types'

const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export type ApiErrorKind = 'network' | 'rate_limit' | 'not_found' | 'validation' | 'server'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null

  constructor(kind: ApiErrorKind, message: string, status: number | null = null) {
    super(message)
    this.kind = kind
    this.status = status
  }
}

function kindFor(status: number): ApiErrorKind {
  if (status === 429) return 'rate_limit'
  if (status === 404) return 'not_found'
  if (status === 422) return 'validation'
  return 'server'
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json()
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      return typeof detail === 'string' ? detail : JSON.stringify(detail)
    }
  } catch {
    // not JSON; fall through
  }
  return res.statusText || `HTTP ${res.status}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'content-type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError('network', 'Could not reach the server.')
  }
  if (!res.ok) throw new ApiError(kindFor(res.status), await detailOf(res), res.status)
  return (await res.json()) as T
}

export const api = {
  databases: () => request<DatabaseInfo[]>('/api/databases'),
  examples: (dbId: string) =>
    request<ExamplesResponse>(`/api/examples?db_id=${encodeURIComponent(dbId)}`),
  query: (body: QueryRequest) =>
    request<QueryResponse>('/api/query', { method: 'POST', body: JSON.stringify(body) }),
}
