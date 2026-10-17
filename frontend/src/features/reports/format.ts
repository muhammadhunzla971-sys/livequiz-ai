import type { Report } from '../../lib/types'

/** 4200 -> "4.2s". Missing or zero values show a dash so an empty cell never reads as "0.0s". */
export function fmtSeconds(ms: number | null | undefined): string {
  return ms ? `${(ms / 1000).toFixed(1)}s` : '–'
}

const LETTERS = ['A', 'B', 'C', 'D', 'E']
/** Option ids are letters A-E; the position decides the colour/shape, same as in the live game. */
export function optionIndex(id: string, fallback: number): number {
  const i = LETTERS.indexOf(id)
  return i >= 0 ? i : fallback
}

/** Students who may need help: they tried, but got under half right. */
export function needsSupport(s: Report['per_student'][number]): boolean {
  return (s.answered ?? 1) > 0 && s.accuracy_pct < 50
}

/** Students who joined but never answered anything (absent or just watching). */
export function noAnswers(s: Report['per_student'][number]): boolean {
  return s.answered === 0
}

export function questionBadge(
  q: Report['per_question'][number],
  r: Report,
): 'hardest' | 'easiest' | null {
  if (r.per_question.length < 3) return null
  if (r.hardest.includes(q.question_id)) return 'hardest'
  if (r.easiest.includes(q.question_id)) return 'easiest'
  return null
}

/** The wrong option most students picked, if it is a real pattern (2+ students and 30%+ of answers). */
export function topWrongOption(
  q: Pick<Report['per_question'][number], 'distribution' | 'correct_option_ids' | 'answered'>,
): { id: string; count: number } | null {
  let best: { id: string; count: number } | null = null
  for (const [id, raw] of Object.entries(q.distribution)) {
    const count = Number(raw)
    if (q.correct_option_ids.includes(id) || count < 2) continue
    if (!best || count > best.count) best = { id, count }
  }
  return best && q.answered > 0 && best.count / q.answered >= 0.3 ? best : null
}

/** Saves a Blob as a file download. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
