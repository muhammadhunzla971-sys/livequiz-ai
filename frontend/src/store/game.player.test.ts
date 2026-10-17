import { describe, expect, it } from 'vitest'
import type { Envelope } from '../lib/types'
import { type GameState, reduce } from './game'

const base = (): GameState =>
  ({
    role: 'player',
    conn: 'open',
    closeCode: null,
    phase: null,
    title: '',
    pin: '',
    locked: false,
    settings: null,
    players: [],
    playersCount: 0,
    question: null,
    endAt: 0,
    remainingMs: null,
    answered: 0,
    distribution: {},
    myChoice: null,
    ackReason: null,
    reveal: null,
    you: null,
    leaderboard: [],
    totalPlayers: 0,
    isLast: false,
    podium: [],
    me: null,
    finishReason: null,
    error: null,
    seq: 0,
  }) as GameState

const env = (type: string, payload: Record<string, unknown>): Envelope => ({
  v: 1,
  type,
  seq: 1,
  ts: 0,
  payload,
})
const apply = (s: GameState, e: Envelope): GameState => ({ ...s, ...reduce(s, e) })

const question = {
  index: 0,
  total: 2,
  question_id: 'q1',
  type: 'mcq',
  text: 'Q?',
  options: [
    { id: 'A', text: 'a' },
    { id: 'B', text: 'b' },
  ],
  time_limit_sec: 20,
  points: 1000,
  started_at: 1,
  question_end_at: 20001,
  server_time: 1,
}

describe('player flow', () => {
  it('lobby -> question -> ack -> reveal with my result', () => {
    let s = apply(
      base(),
      env('room.state', { state: 'lobby', title: 'T', locked: false, players_count: 2 }),
    )
    expect(s.phase).toBe('lobby')
    expect(s.playersCount).toBe(2)

    s = apply(s, env('question.show', question))
    expect(s.phase).toBe('question_active')
    expect(s.myChoice).toBeNull()

    s = { ...s, myChoice: ['B'] } // what choose() does after sending
    s = apply(s, env('answer.ack', { accepted: true }))
    expect(s.myChoice).toEqual(['B'])

    s = apply(
      s,
      env('answer.reveal', {
        correct_option_ids: ['B'],
        explanation: 'x',
        you: { answered: true, chosen: ['B'], is_correct: true, points: 800, score: 800, rank: 1 },
      }),
    )
    expect(s.phase).toBe('question_closed')
    expect(s.you?.points).toBe(800)
    expect(s.reveal?.correct_option_ids).toEqual(['B'])
  })

  it('a rejected answer unlocks the buttons, a duplicate keeps the first choice', () => {
    const s0 = { ...base(), phase: 'question_active' as const, myChoice: ['A'] }
    const late = apply(s0, env('answer.ack', { accepted: false, reason: 'late' }))
    expect(late.myChoice).toBeNull()
    expect(late.ackReason).toBe('late')
    const dup = apply(s0, env('answer.ack', { accepted: false, reason: 'duplicate' }))
    expect(dup.myChoice).toEqual(['A'])
  })

  it('reconnect snapshot restores an answer that was already sent', () => {
    const s = apply(
      base(),
      env('room.state', {
        state: 'question_active',
        title: 'T',
        locked: false,
        players_count: 3,
        question,
        my_answer: { answered: true, chosen: ['A'] },
      }),
    )
    expect(s.phase).toBe('question_active')
    expect(s.myChoice).toEqual(['A'])
    expect(s.endAt).toBe(20001)
  })

  it('pause freezes the clock and resume restores it', () => {
    let s = apply(base(), env('question.show', question))
    s = apply(s, env('game.paused', { remaining_ms: 7000 }))
    expect(s.phase).toBe('paused')
    expect(s.remainingMs).toBe(7000)
    s = apply(s, env('game.resumed', { question_end_at: 30000 }))
    expect(s.phase).toBe('question_active')
    expect(s.remainingMs).toBeNull()
    expect(s.endAt).toBe(30000)
  })

  it('kicked and finished events', () => {
    expect(apply(base(), env('player.kicked', {})).error).toBe('kicked')
    const s = apply(
      base(),
      env('game.finished', {
        reason: 'completed',
        podium: [],
        leaderboard: [],
        total_players: 2,
        me: { nickname: 'Ada', rank: 2, score: 5 },
      }),
    )
    expect(s.phase).toBe('finished')
    expect(s.me?.rank).toBe(2)
  })
})
