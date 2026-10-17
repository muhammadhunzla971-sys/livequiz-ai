export type QuestionType = 'mcq' | 'true_false' | 'multi_select'
export type Level = 'beginner' | 'intermediate' | 'advanced'

export interface Option {
  id: string
  text: string
}

export interface QuestionDraft {
  id?: string | null
  type: QuestionType
  text: string
  options: Option[]
  correct_option_ids: string[]
  explanation: string
  difficulty: number
  bloom_level: 'remember' | 'understand' | 'apply' | 'analyze'
  subtopic: string
  time_limit_sec: number
  points: number
}

export interface Quiz {
  id: string
  title: string
  topic: string
  level: Level
  learning_goal: string
  language: string
  status: 'draft' | 'published'
  tags: string[]
  scoring_config: Record<string, number | boolean>
  questions: (QuestionDraft & { id: string; position: number })[]
  updated_at: string
}

export interface QuizSummary {
  id: string
  title: string
  topic: string
  level: string
  status: string
  language: string
  question_count: number
  tags: string[]
  updated_at: string
}

export interface GenerateRequest {
  topic: string
  level: Level
  learning_goal: string
  num_questions: number
  question_types: QuestionType[]
  time_limit_sec: number
  language: string
  force_regenerate?: boolean
}

export interface SessionOut {
  id: string
  quiz_id: string
  pin: string
  status: string
  join_url: string
  title: string
  players: number
}

export interface JoinOut {
  room_id: string
  player_id: string
  player_token: string
  nickname: string
  rejoined: boolean
}

// ---- realtime -----------------------------------------------------------------------------
export interface Envelope<T = Record<string, unknown>> {
  v: number
  type: string
  seq: number
  ts: number
  payload: T
}

export interface PublicQuestion {
  index: number
  total: number
  question_id: string
  type: QuestionType
  text: string
  options: Option[]
  time_limit_sec: number
  points: number
  started_at: number
  question_end_at: number
  server_time: number
}

export interface LeaderboardEntry {
  rank: number
  player_id: string
  nickname: string
  avatar: string
  score: number
  streak: number
  rank_change: number
}

export interface YouResult {
  answered: boolean
  chosen: string[]
  is_correct: boolean
  accuracy: number
  points: number
  streak: number
  score: number
  rank: number | null
  rank_change: number
}

export interface RosterPlayer {
  id: string
  nickname: string
  avatar: string
  connected?: boolean
}

export interface RoomSettings {
  auto_reveal: boolean
  live_leaderboard: boolean
  show_distribution: boolean
  auto_close: boolean
}

export type RoomPhase =
  | 'created'
  | 'lobby'
  | 'question_active'
  | 'question_closed'
  | 'leaderboard'
  | 'paused'
  | 'finished'
  | 'archived'

export interface Reveal {
  correct_option_ids: string[]
  explanation: string
  distribution: Record<string, number>
  answered?: number
  total?: number
  correct_count?: number
  avg_response_ms?: number
}

export interface FinalMe {
  nickname: string
  rank: number | null
  score: number
  correct: number
  answered: number
  total_questions: number
  accuracy_pct: number
  best_streak: number
}

export interface ReportListItem {
  id: string
  quiz_id: string
  title: string
  pin: string
  players: number
  created_at: string
}

export interface Report {
  session_id?: string
  language?: string
  title: string
  topic: string
  overall: {
    players: number
    questions: number
    avg_score: number
    accuracy_pct: number
    avg_response_ms: number
    participation_pct: number
  }
  per_question: {
    question_id: string
    position: number
    text: string
    subtopic: string
    type?: string
    correct?: number
    accuracy_pct: number
    avg_response_ms: number
    answered: number
    distribution: Record<string, number>
    correct_option_ids: string[]
  }[]
  per_student: {
    player_id: string
    nickname: string
    avatar?: string
    answered?: number
    rank: number | null
    score: number
    correct: number
    accuracy_pct: number
    avg_response_ms: number
  }[]
  subtopics: { subtopic: string; accuracy_pct: number; attempts: number }[]
  weak_subtopics: { subtopic: string; accuracy_pct: number; attempts: number }[]
  hardest: string[]
  easiest: string[]
  ai_summary: {
    class_insight: string
    reteach: string[]
    study_tips: Record<string, string>
  } | null
}

export interface StudentReport {
  nickname: string
  score: number
  rank: number | null
  correct: number
  answered: number
  accuracy_pct: number
  subtopics: { subtopic: string; accuracy_pct: number; attempts: number }[]
  review: {
    question_id: string
    text: string
    options: Option[]
    chosen: string[]
    correct_option_ids: string[]
    explanation: string
    subtopic: string
  }[]
}
