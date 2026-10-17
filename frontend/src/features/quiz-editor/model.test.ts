import { describe, expect, it } from 'vitest'
import {
  addOption,
  moveItem,
  newQuestion,
  removeOption,
  setCorrect,
  setOptionText,
  toPayload,
  validateQuestion,
} from './model'

function filled(type: 'mcq' | 'true_false' | 'multi_select') {
  let q = newQuestion(type)
  q = { ...q, text: 'What does a plant release?' }
  if (type !== 'true_false') q.options.forEach((_, i) => (q = setOptionText(q, i, `Option ${i}`)))
  return q
}

describe('validateQuestion', () => {
  it('flags an empty new question', () => {
    const issues = validateQuestion(newQuestion('mcq'))
    expect(issues.join(' ')).toMatch(/at least 5/)
    expect(issues.join(' ')).toMatch(/needs text/)
  })

  it('accepts a complete mcq', () => {
    expect(validateQuestion(filled('mcq'))).toEqual([])
  })

  it('rejects duplicate options and lazy options', () => {
    let q = filled('mcq')
    q = setOptionText(q, 1, 'option 0')
    expect(validateQuestion(q).join(' ')).toMatch(/different/)
    q = setOptionText(q, 1, 'All of the above')
    expect(validateQuestion(q).join(' ')).toMatch(/all\/none/i)
  })

  it('needs two correct answers for multi-select, and not all of them', () => {
    let q = filled('multi_select')
    q = setCorrect(q, 'B', false)
    expect(validateQuestion(q).join(' ')).toMatch(/at least 2 correct/)
    q = { ...q, correct_option_ids: q.options.map((o) => o.id) }
    expect(validateQuestion(q).join(' ')).toMatch(/Not every option/)
  })

  it('true/false is valid out of the box once it has text', () => {
    expect(validateQuestion({ ...newQuestion('true_false'), text: 'Water boils at 100C' })).toEqual(
      [],
    )
  })
})

describe('options', () => {
  it('single answer types replace the correct answer', () => {
    const q = setCorrect(filled('mcq'), 'C', true)
    expect(q.correct_option_ids).toEqual(['C'])
  })

  it('removing an option re-letters and keeps the correct answer on the same text', () => {
    let q = filled('mcq')
    q = addOption(q) // 5 options A-E
    q = setCorrect(q, 'D', true) // correct = "Option 3"
    q = removeOption(q, 1) // drop B
    expect(q.options.map((o) => o.id)).toEqual(['A', 'B', 'C', 'D'])
    const correctText = q.options.find((o) => o.id === q.correct_option_ids[0])?.text
    expect(correctText).toBe('Option 3')
  })

  it('removing the correct option clears the answer', () => {
    const q = removeOption(addOption(filled('mcq')), 0)
    expect(q.correct_option_ids).toEqual([])
    expect(validateQuestion(q).join(' ')).toMatch(/exactly one/)
  })

  it('enforces option count limits', () => {
    let q = filled('mcq')
    expect(removeOption(removeOption(q, 0), 0).options).toHaveLength(3)
    q = addOption(q)
    expect(addOption(q).options).toHaveLength(5)
    expect(removeOption(newQuestion('true_false'), 0).options).toHaveLength(2)
  })
})

describe('payload and ordering', () => {
  it('omits id for unsaved questions and trims text', () => {
    const q = { ...filled('mcq'), text: '  Spaced question?  ' }
    const p = toPayload(q)
    expect(p).not.toHaveProperty('id')
    expect(p.text).toBe('Spaced question?')
    expect(toPayload({ ...q, id: 'abc' }).id).toBe('abc')
  })

  it('moveItem swaps and ignores out-of-range moves', () => {
    expect(moveItem([1, 2, 3], 0, 1)).toEqual([2, 1, 3])
    expect(moveItem([1, 2, 3], 0, -1)).toEqual([1, 2, 3])
    expect(moveItem([1, 2, 3], 2, 1)).toEqual([1, 2, 3])
  })
})
