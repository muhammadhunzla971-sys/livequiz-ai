import { describe, expect, it } from 'vitest'
import type { Envelope } from '../lib/types'
import { type GameState, reduce } from './game'

const base = (): GameState =>
  ({
    role: 'host',
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

describe('host view of the game stream', () => {
  it('builds the lobby from a snapshot and tracks joins and kicks', () => {
    let s = base()
    s = {
      ...s,
      ...reduce(
        s,
        env('room.state', {
          state: 'lobby',
          title: 'Bio',
          locked: false,
          players_count: 0,
          pin: '123456',
          players: [],
          settings: {},
        }),
      ),
    }
    expect(s.pin).toBe('123456')
    s = {
      ...s,
      ...reduce(
        s,
        env('player.joined', { player: { id: 'p1', nickname: 'Ada', avatar: '🦊' }, count: 1 }),
      ),
    }
    expect(s.players).toHaveLength(1)
    expect(s.playersCount).toBe(1)
    s = { ...s, ...reduce(s, env('player.left', { player_id: 'p1', reason: 'kicked', count: 0 })) }
    expect(s.players).toHaveLength(0)
  })

  it('goes question -> reveal -> leaderboard -> finished', () => {
    let s = base()
    const q = {
      index: 0,
      total: 2,
      question_id: 'q1',
      type: 'mcq',
      text: 'Q?',
      options: [{ id: 'A', text: 'a' }],
      time_limit_sec: 20,
      points: 1000,
      started_at: 0,
      question_end_at: 99,
      server_time: 0,
    }
    s = { ...s, ...reduce(s, env('question.show', q)) }
    expect(s.phase).toBe('question_active')
    expect(s.endAt).toBe(99)
    s = { ...s, ...reduce(s, env('question.tick', { answered: 3, distribution: { A: '3' } })) }
    expect(s.answered).toBe(3)
    expect(s.distribution).toEqual({ A: 3 })
    s = {
      ...s,
      ...reduce(
        s,
        env('answer.reveal', {
          correct_option_ids: ['A'],
          explanation: 'because',
          distribution: { A: '3' },
          answered: 3,
          total: 3,
          correct_count: 3,
        }),
      ),
    }
    expect(s.phase).toBe('question_closed')
    expect(s.reveal?.correct_option_ids).toEqual(['A'])
    s = {
      ...s,
      ...reduce(
        s,
        env('leaderboard.update', {
          entries: [],
          total_players: 3,
          is_last: true,
          phase: 'leaderboard',
        }),
      ),
    }
    expect(s.phase).toBe('leaderboard')
    expect(s.isLast).toBe(true)
    s = {
      ...s,
      ...reduce(
        s,
        env('game.finished', {
          podium: [],
          leaderboard: [],
          total_players: 3,
          reason: 'completed',
        }),
      ),
    }
    expect(s.phase).toBe('finished')
  })

  it('pause keeps the remaining time frozen, resume restores the clock', () => {
    let s = base()
    s = { ...s, ...reduce(s, env('game.paused', { remaining_ms: 8000 })) }
    expect(s.phase).toBe('paused')
    expect(s.remainingMs).toBe(8000)
    s = { ...s, ...reduce(s, env('game.resumed', { question_end_at: 500 })) }
    expect(s.phase).toBe('question_active')
    expect(s.remainingMs).toBeNull()
    expect(s.endAt).toBe(500)
  })

  it('surfaces server errors by code', () => {
    const s = { ...base(), ...reduce(base(), env('error', { code: 'no_players' })) }
    expect(s.error).toBe('no_players')
  })
})
