import type {
  GenerateRequest,
  JoinOut,
  Quiz,
  QuizSummary,
  ReportListItem,
  Report,
  SessionOut,
  StudentReport,
} from './types'

import { API_BASE } from './config'

const ACCESS = 'lq.access'
const REFRESH = 'lq.refresh'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* storage can be blocked (private mode); the session just won't persist */
  }
}

export const tokens = {
  access: () => read(ACCESS),
  set(access: string, refresh: string) {
    write(ACCESS, access)
    write(REFRESH, refresh)
  },
  clear() {
    write(ACCESS, null)
    write(REFRESH, null)
  },
  hasSession: () => read(REFRESH) !== null,
}

export class ApiError extends Error {
  status: number
  code?: string
  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

function describe(detail: unknown, fallback: string): { message: string; code?: string } {
  if (typeof detail === 'string') return { message: detail }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const d = detail as { message: string; code?: string }
    return { message: d.message, code: d.code }
  }
  if (Array.isArray(detail) && typeof detail[0] === 'string')
    return { message: detail.slice(0, 5).join('\n') }
  if (Array.isArray(detail) && detail[0]?.msg) return { message: String(detail[0].msg) }
  return { message: fallback }
}

let refreshing: Promise<boolean> | null = null
async function refreshTokens(): Promise<boolean> {
  const refresh = read(REFRESH)
  if (!refresh) return false
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      })
      if (!r.ok) return false
      const t = await r.json()
      tokens.set(t.access_token, t.refresh_token)
      return true
    } catch {
      return false
    } finally {
      setTimeout(() => (refreshing = null), 0)
    }
  })()
  return refreshing
}

interface Opts {
  method?: string
  body?: unknown
  token?: string | null
  raw?: boolean
}

export async function request<T>(path: string, opts: Opts = {}, retried = false): Promise<T> {
  const headers: Record<string, string> = {}
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
  const token = opts.token === undefined ? tokens.access() : opts.token
  if (token) headers.Authorization = `Bearer ${token}`
  let res: Response
  try {
    res = await fetch(API_BASE + path, {
      method: opts.method ?? 'GET',
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.')
  }
  if (res.status === 401 && !retried && opts.token === undefined && (await refreshTokens())) {
    return request<T>(path, opts, true)
  }
  if (!res.ok) {
    let detail: unknown
    try {
      detail = (await res.json()).detail
    } catch {
      /* non-JSON error body */
    }
    const { message, code } = describe(detail, `Request failed (${res.status})`)
    if (res.status === 401 && opts.token === undefined) tokens.clear()
    throw new ApiError(res.status, message, code)
  }
  if (res.status === 204) return undefined as T
  if (opts.raw) return (await res.blob()) as T
  return (await res.json()) as T
}

export const api = {
  register: (email: string, password: string, display_name: string) =>
    request<{ access_token: string; refresh_token: string }>('/api/auth/register', {
      method: 'POST',
      body: { email, password, display_name },
      token: null,
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
      token: null,
    }),
  me: () => request<{ id: string; email: string; display_name: string }>('/api/auth/me'),
  listQuizzes: (q = '', tag = '') =>
    request<QuizSummary[]>(
      `/api/quizzes?${new URLSearchParams({ ...(q && { q }), ...(tag && { tag }) })}`,
    ),
  getQuiz: (id: string) => request<Quiz>(`/api/quizzes/${id}`),
  exportQuizCsv: (id: string) => request<Blob>(`/api/quizzes/${id}/export.csv`, { raw: true }),
  importQuizCsv: (title: string, csv: string) =>
    request<Quiz>('/api/quizzes/import', { method: 'POST', body: { title, csv } }),
  createQuiz: (body: unknown) => request<Quiz>('/api/quizzes', { method: 'POST', body }),
  updateQuiz: (id: string, body: unknown) =>
    request<Quiz>(`/api/quizzes/${id}`, { method: 'PATCH', body }),
  deleteQuiz: (id: string) => request<void>(`/api/quizzes/${id}`, { method: 'DELETE' }),
  duplicateQuiz: (id: string) => request<Quiz>(`/api/quizzes/${id}/duplicate`, { method: 'POST' }),
  regenerateQuestion: (quizId: string, qid: string, feedback: string) =>
    request<Quiz>(`/api/quizzes/${quizId}/questions/${qid}/regenerate`, {
      method: 'POST',
      body: { feedback },
    }),
  createSession: (quiz_id: string, settings: Record<string, boolean> = {}) =>
    request<SessionOut>('/api/sessions', { method: 'POST', body: { quiz_id, ...settings } }),
  listSessions: () => request<SessionOut[]>('/api/sessions'),
  lookupPin: (pin: string) =>
    request<{ title: string; state: string; locked: boolean }>(`/api/join/${pin}`, {
      token: null,
    }),
  join: (pin: string, nickname: string, avatar: string, device_id: string) =>
    request<JoinOut>('/api/join', {
      method: 'POST',
      body: { pin, nickname, avatar, device_id },
      token: null,
    }),
  listReports: () => request<ReportListItem[]>('/api/reports'),
  report: (sid: string) => request<Report>(`/api/sessions/${sid}/report`),
  summarize: (sid: string) =>
    request<NonNullable<Report['ai_summary']>>(`/api/sessions/${sid}/report/summary`, {
      method: 'POST',
    }),
  download: (sid: string, kind: 'csv' | 'pdf') =>
    request<Blob>(`/api/sessions/${sid}/report.${kind}`, { raw: true }),
  deleteSession: (sid: string) => request<void>(`/api/sessions/${sid}`, { method: 'DELETE' }),
  myReport: (playerToken: string) =>
    request<StudentReport>('/api/play/report', { token: playerToken }),
}

/** Streams quiz generation progress over SSE using fetch (EventSource can't send headers). */
export async function generateQuizStream(
  body: GenerateRequest,
  onProgress: (message: string) => void,
  signal?: AbortSignal,
): Promise<Quiz> {
  const start = (): Promise<Response> =>
    fetch(`${API_BASE}/api/quizzes/generate/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${tokens.access() ?? ''}`,
      },
      body: JSON.stringify(body),
      signal,
    })
  let res: Response
  try {
    res = await start()
    // The access token only lives 15 minutes: refresh it once and retry, like request() does.
    if (res.status === 401 && (await refreshTokens())) res = await start()
  } catch (ex) {
    if (ex instanceof DOMException && ex.name === 'AbortError') throw ex
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.')
  }
  if (res.status === 401) {
    tokens.clear()
    throw new ApiError(401, 'Your session expired. Please log in again.')
  }
  if (!res.ok || !res.body) {
    let detail: unknown
    try {
      detail = (await res.json()).detail
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, describe(detail, 'Could not start generation').message)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const block = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const event = /^event: (.*)$/m.exec(block)?.[1]
      const data = /^data: (.*)$/m.exec(block)?.[1]
      if (!event || !data) continue
      const parsed = JSON.parse(data)
      if (event === 'progress') onProgress(parsed.message ?? '')
      else if (event === 'done') return parsed as Quiz
      else if (event === 'error') {
        throw new ApiError(
          parsed.status ?? 500,
          describe(parsed.detail, 'Generation failed').message,
        )
      }
    }
  }
  throw new ApiError(0, 'The connection closed before the quiz was ready.')
}
