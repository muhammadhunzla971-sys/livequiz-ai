import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, generateQuizStream, tokens } from './api'

const req = { topic: 'x' } as never
const sse = (events: string) =>
  new Response(events, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
const quiz = { id: 'q1', title: 'T', questions: [] }
const done = `event: done\ndata: ${JSON.stringify(quiz)}\n\n`

describe('generateQuizStream auth', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    tokens.set('old-access', 'good-refresh')
  })
  afterEach(() => vi.unstubAllGlobals())

  it('refreshes an expired access token and retries once', async () => {
    const calls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${url}|${(init?.headers as Record<string, string>)?.Authorization ?? ''}`)
        if (url.endsWith('/generate/stream')) {
          const auth = (init?.headers as Record<string, string>).Authorization
          return auth === 'Bearer new-access'
            ? sse(done)
            : new Response(JSON.stringify({ detail: 'Invalid or expired token' }), { status: 401 })
        }
        return new Response(JSON.stringify({ access_token: 'new-access', refresh_token: 'r2' }))
      }),
    )
    const out = await generateQuizStream(req, () => {})
    expect(out.id).toBe('q1')
    expect(calls.filter((c) => c.includes('/generate/stream'))).toHaveLength(2)
    expect(tokens.access()).toBe('new-access')
  })

  it('asks the teacher to log in again when the refresh token is dead', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'nope' }), { status: 401 })),
    )
    await expect(generateQuizStream(req, () => {})).rejects.toMatchObject({
      status: 401,
      message: 'Your session expired. Please log in again.',
    })
    expect(tokens.access()).toBeNull()
  })

  it('does not retry on other errors', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ detail: 'busy' }), { status: 503 }))
    vi.stubGlobal('fetch', f)
    await expect(generateQuizStream(req, () => {})).rejects.toBeInstanceOf(ApiError)
    expect(f).toHaveBeenCalledTimes(1)
  })
})
