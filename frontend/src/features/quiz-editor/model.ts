import type { Option, QuestionDraft, QuestionType, Quiz } from '../../lib/types'

/** A question being edited. `key` is a stable client id; `id` exists only once saved. */
export type EditableQuestion = QuestionDraft & { key: string }

export const LETTERS = ['A', 'B', 'C', 'D', 'E']
const LAZY = ['all of the above', 'none of the above', 'both a and b', 'all of these']

let counter = 0
const newKey = () => `new-${Date.now().toString(36)}-${++counter}`

export function newQuestion(type: QuestionType): EditableQuestion {
  const base = {
    key: newKey(),
    type,
    text: '',
    explanation: '',
    difficulty: 1,
    bloom_level: 'remember' as const,
    subtopic: '',
    time_limit_sec: 20,
    points: 1000,
  }
  if (type === 'true_false')
    return {
      ...base,
      options: [
        { id: 'A', text: 'True' },
        { id: 'B', text: 'False' },
      ],
      correct_option_ids: ['A'],
    }
  return {
    ...base,
    options: LETTERS.slice(0, 4).map((id) => ({ id, text: '' })),
    correct_option_ids: type === 'multi_select' ? ['A', 'B'] : ['A'],
  }
}

export function fromQuiz(quiz: Quiz): EditableQuestion[] {
  return [...quiz.questions]
    .sort((a, b) => a.position - b.position)
    .map((q) => ({ ...q, key: q.id }))
}

/** Re-letter options A, B, C... in order, keeping the correct answers pointing at the same text. */
function relabel(
  q: EditableQuestion,
  options: Option[],
  correctTexts: Set<number>,
): EditableQuestion {
  const next = options.map((o, i) => ({ ...o, id: LETTERS[i] }))
  return {
    ...q,
    options: next,
    correct_option_ids: next.filter((_, i) => correctTexts.has(i)).map((o) => o.id),
  }
}

export function maxOptions(type: QuestionType): number {
  return type === 'true_false' ? 2 : 5
}
export function minOptions(type: QuestionType): number {
  return type === 'true_false' ? 2 : type === 'multi_select' ? 4 : 3
}

export function addOption(q: EditableQuestion): EditableQuestion {
  if (q.options.length >= maxOptions(q.type)) return q
  const correct = new Set(q.options.map((o, i) => (q.correct_option_ids.includes(o.id) ? i : -1)))
  return relabel(q, [...q.options, { id: '', text: '' }], correct)
}

export function removeOption(q: EditableQuestion, index: number): EditableQuestion {
  if (q.options.length <= minOptions(q.type)) return q
  const correct = new Set<number>()
  q.options.forEach((o, i) => {
    if (i === index || !q.correct_option_ids.includes(o.id)) return
    correct.add(i < index ? i : i - 1)
  })
  return relabel(
    q,
    q.options.filter((_, i) => i !== index),
    correct,
  )
}

export function setOptionText(q: EditableQuestion, index: number, text: string): EditableQuestion {
  return { ...q, options: q.options.map((o, i) => (i === index ? { ...o, text } : o)) }
}

/** Single-answer types replace the answer; multi-select toggles it. */
export function setCorrect(q: EditableQuestion, optionId: string, on: boolean): EditableQuestion {
  if (q.type !== 'multi_select') return { ...q, correct_option_ids: [optionId] }
  const set = new Set(q.correct_option_ids)
  if (on) set.add(optionId)
  else set.delete(optionId)
  return { ...q, correct_option_ids: q.options.map((o) => o.id).filter((id) => set.has(id)) }
}

/** Mirrors the server rules so problems show up before Save instead of as a 422. */
export function validateQuestion(q: EditableQuestion): string[] {
  const issues: string[] = []
  if (q.text.trim().length < 5) issues.push('Question text must be at least 5 characters.')
  const texts = q.options.map((o) => o.text.trim().toLowerCase())
  if (texts.some((t) => !t)) issues.push('Every option needs text.')
  if (new Set(texts.filter(Boolean)).size !== texts.filter(Boolean).length)
    issues.push('Options must be different from each other.')
  if (texts.some((t) => LAZY.some((l) => t.includes(l))))
    issues.push('Avoid “all/none of the above” options.')
  const c = q.correct_option_ids.length
  if (q.type === 'multi_select') {
    if (c < 2) issues.push('Multi-select needs at least 2 correct answers.')
    if (c === q.options.length) issues.push('Not every option can be correct.')
  } else if (c !== 1) {
    issues.push('Pick exactly one correct answer.')
  }
  if (q.time_limit_sec < 5 || q.time_limit_sec > 120)
    issues.push('Time limit must be 5 to 120 seconds.')
  if (q.points < 0 || q.points > 10000) issues.push('Points must be 0 to 10000.')
  return issues
}

export function toPayload(q: EditableQuestion) {
  return {
    ...(q.id ? { id: q.id } : {}),
    type: q.type,
    text: q.text.trim(),
    options: q.options.map((o) => ({ id: o.id, text: o.text.trim() })),
    correct_option_ids: q.correct_option_ids,
    explanation: q.explanation.trim(),
    difficulty: q.difficulty,
    bloom_level: q.bloom_level,
    subtopic: q.subtopic.trim(),
    time_limit_sec: q.time_limit_sec,
    points: q.points,
  }
}

export function moveItem<T>(arr: T[], from: number, dir: -1 | 1): T[] {
  const to = from + dir
  if (to < 0 || to >= arr.length) return arr
  const next = [...arr]
  ;[next[from], next[to]] = [next[to], next[from]]
  return next
}
