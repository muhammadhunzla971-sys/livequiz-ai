import { create } from 'zustand'
import type {
  Envelope,
  FinalMe,
  LeaderboardEntry,
  PublicQuestion,
  Reveal,
  RoomPhase,
  RoomSettings,
  RosterPlayer,
  YouResult,
} from '../lib/types'
import type { ConnStatus } from '../ws/client'

export interface GameState {
  role: 'host' | 'player' | null
  conn: ConnStatus
  closeCode: number | null
  phase: RoomPhase | null
  title: string
  pin: string
  locked: boolean
  settings: RoomSettings | null
  players: RosterPlayer[]
  playersCount: number
  question: PublicQuestion | null
  /** Server-clock timestamp when the question ends. */
  endAt: number
  remainingMs: number | null // set while paused
  answered: number
  distribution: Record<string, number>
  myChoice: string[] | null
  ackReason: string | null
  reveal: Reveal | null
  you: YouResult | null
  leaderboard: LeaderboardEntry[]
  totalPlayers: number
  isLast: boolean
  podium: LeaderboardEntry[]
  me: FinalMe | null
  finishReason: string | null
  error: string | null
  seq: number
}

const initial: GameState = {
  role: null,
  conn: 'connecting',
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
}

interface Actions {
  reset: (role: 'host' | 'player') => void
  setConn: (conn: ConnStatus, code?: number) => void
  choose: (ids: string[]) => void
  apply: (msg: Envelope) => void
}

type P = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

const toDist = (d: Record<string, string | number> | undefined): Record<string, number> =>
  Object.fromEntries(Object.entries(d ?? {}).map(([k, v]) => [k, Number(v)]))

/** Pure reducer: server event -> state patch. Exported for unit tests. */
export function reduce(s: GameState, msg: Envelope): Partial<GameState> {
  const p = msg.payload as P
  switch (msg.type) {
    case 'room.state': {
      const patch: Partial<GameState> = {
        phase: p.state,
        title: p.title,
        locked: p.locked,
        settings: p.settings,
        playersCount: p.players_count,
        pin: p.pin ?? s.pin,
        players: p.players ?? s.players,
        leaderboard: p.leaderboard ?? [],
        totalPlayers: p.total_players ?? p.players_count,
        podium: p.podium ?? [],
        me: p.me ?? null,
        question: null,
        reveal: null,
        you: null,
        remainingMs: null,
        error: null,
        answered: 0,
        distribution: {},
        myChoice: null,
        ackReason: null,
      }
      if (p.question) {
        patch.question = p.question
        patch.endAt = p.question.question_end_at
        patch.answered = p.answered ?? 0
        patch.distribution = toDist(p.distribution)
        if (p.state === 'paused') patch.remainingMs = p.remaining_ms ?? null
        if (p.my_answer?.answered) patch.myChoice = p.my_answer.chosen
      }
      if (p.reveal) patch.reveal = { ...p.reveal, distribution: toDist(p.reveal.distribution) }
      if (p.you) patch.you = p.you
      return patch
    }
    case 'player.joined': {
      if (s.role !== 'host' && s.phase !== 'lobby') return {}
      const player = p.player as RosterPlayer
      const known = s.players.some((x) => x.id === player.id)
      const players = known
        ? s.players.map((x) =>
            x.id === player.id ? { ...x, ...player, connected: p.connected ?? x.connected } : x,
          )
        : [...s.players, { ...player, connected: true }]
      return { players, playersCount: p.count ?? players.length }
    }
    case 'player.left':
      return {
        players:
          p.reason === 'kicked'
            ? s.players.filter((x) => x.id !== p.player_id)
            : s.players.map((x) => (x.id === p.player_id ? { ...x, connected: false } : x)),
        playersCount: p.count ?? s.playersCount,
      }
    case 'player.kicked':
      return { error: 'kicked' }
    case 'game.started':
      return { phase: 'question_active' }
    case 'question.show':
      return {
        phase: 'question_active',
        question: p as PublicQuestion,
        endAt: p.question_end_at,
        answered: 0,
        distribution: {},
        myChoice: null,
        ackReason: null,
        reveal: null,
        you: null,
        remainingMs: null,
      }
    case 'question.tick':
      return {
        answered: p.answered ?? s.answered,
        endAt: p.question_end_at ?? s.endAt,
        distribution: p.distribution ? toDist(p.distribution) : s.distribution,
      }
    case 'question.closed':
      return { phase: 'question_closed', answered: p.answered ?? s.answered }
    case 'answer.ack':
      return p.accepted
        ? { ackReason: null }
        : { ackReason: p.reason, myChoice: p.reason === 'duplicate' ? s.myChoice : null }
    case 'answer.reveal':
      return {
        phase: 'question_closed',
        reveal: {
          correct_option_ids: p.correct_option_ids,
          explanation: p.explanation,
          distribution: toDist(p.distribution),
          answered: p.answered,
          total: p.total,
          correct_count: p.correct_count,
          avg_response_ms: p.avg_response_ms,
        },
        you: p.you ?? null,
      }
    case 'leaderboard.update':
      return {
        leaderboard: p.entries,
        totalPlayers: p.total_players,
        isLast: p.is_last,
        ...(p.phase === 'leaderboard' ? { phase: 'leaderboard' as const } : {}),
      }
    case 'game.paused':
      return { phase: 'paused', remainingMs: p.remaining_ms }
    case 'game.resumed':
      return { phase: 'question_active', endAt: p.question_end_at, remainingMs: null }
    case 'game.finished':
      return {
        phase: 'finished',
        podium: p.podium,
        leaderboard: p.leaderboard,
        totalPlayers: p.total_players,
        me: p.me ?? null,
        finishReason: p.reason,
      }
    case 'error':
      return { error: p.code }
    default:
      return {}
  }
}

export const useGame = create<GameState & Actions>((set) => ({
  ...initial,
  reset: (role) => set({ ...initial, role }),
  setConn: (conn, code) => set({ conn, closeCode: code ?? null }),
  choose: (ids) => set({ myChoice: ids, ackReason: null }),
  apply: (msg) => set((s) => ({ ...reduce(s, msg), seq: msg.seq })),
}))
