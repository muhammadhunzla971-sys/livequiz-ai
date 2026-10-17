import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PublicQuestion, Reveal, YouResult } from '../../lib/types'
import AnswerPad from './AnswerPad'
import ResultPanel, { outcomeOf } from './ResultPanel'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, d: string) => d }),
}))

const q = (type: PublicQuestion['type']): PublicQuestion => ({
  index: 0,
  total: 3,
  question_id: 'q1',
  type,
  text: 'Pick',
  options: [
    { id: 'A', text: 'Alpha' },
    { id: 'B', text: 'Beta' },
    { id: 'C', text: 'Gamma' },
  ],
  time_limit_sec: 20,
  points: 1000,
  started_at: 0,
  question_end_at: 0,
  server_time: 0,
})

const you = (o: Partial<YouResult> = {}): YouResult => ({
  answered: true,
  chosen: ['B'],
  is_correct: true,
  accuracy: 1,
  points: 900,
  streak: 1,
  score: 900,
  rank: 1,
  rank_change: 0,
  ...o,
})
const reveal: Reveal = { correct_option_ids: ['B'], explanation: 'Because B.', distribution: {} }

describe('AnswerPad', () => {
  it('sends a single-choice answer immediately on tap', () => {
    const onSubmit = vi.fn()
    render(<AnswerPad question={q('mcq')} chosen={null} disabled={false} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('button', { name: /Beta/ }))
    expect(onSubmit).toHaveBeenCalledWith(['B'])
  })

  it('locks after answering: no second submit, chosen stays pressed', () => {
    const onSubmit = vi.fn()
    render(<AnswerPad question={q('mcq')} chosen={['B']} disabled={false} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('button', { name: /Alpha/ }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Beta/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('does nothing while disabled (paused)', () => {
    const onSubmit = vi.fn()
    render(<AnswerPad question={q('mcq')} chosen={null} disabled onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('button', { name: /Alpha/ }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('multi select toggles and only sends on lock in', () => {
    const onSubmit = vi.fn()
    render(
      <AnswerPad question={q('multi_select')} chosen={null} disabled={false} onSubmit={onSubmit} />,
    )
    const lock = screen.getByRole('button', { name: 'Lock in answer' })
    expect(lock).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Alpha/ }))
    fireEvent.click(screen.getByRole('button', { name: /Gamma/ }))
    fireEvent.click(screen.getByRole('button', { name: /Alpha/ })) // toggle off
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.click(lock)
    expect(onSubmit).toHaveBeenCalledWith(['C'])
  })

  it('keys 1-3 pick an option', () => {
    const onSubmit = vi.fn()
    render(<AnswerPad question={q('mcq')} chosen={null} disabled={false} onSubmit={onSubmit} />)
    fireEvent.keyDown(window, { key: '3' })
    expect(onSubmit).toHaveBeenCalledWith(['C'])
  })
})

describe('outcomeOf', () => {
  it('classifies every result', () => {
    expect(outcomeOf(null, null)).toBe('waiting')
    expect(outcomeOf(reveal, you())).toBe('correct')
    expect(outcomeOf(reveal, you({ is_correct: false, accuracy: 0.5 }))).toBe('partial')
    expect(outcomeOf(reveal, you({ is_correct: false, accuracy: 0 }))).toBe('wrong')
    expect(outcomeOf(reveal, you({ answered: false, chosen: [], is_correct: false }))).toBe(
      'missed',
    )
  })
})

describe('ResultPanel', () => {
  it('shows points, rank and the explanation for a correct answer', () => {
    render(<ResultPanel question={q('mcq')} reveal={reveal} you={you()} myChoice={['B']} />)
    expect(screen.getByText('Correct!')).toBeInTheDocument()
    expect(screen.getByText(/\+900/)).toBeInTheDocument()
    expect(screen.getByText('Because B.')).toBeInTheDocument()
    expect(screen.getByLabelText('Correct answer')).toBeInTheDocument()
  })

  it('waits for the reveal after time is up', () => {
    render(<ResultPanel question={q('mcq')} reveal={null} you={null} myChoice={['A']} />)
    expect(screen.getByText(/Waiting for the teacher/)).toBeInTheDocument()
  })

  it('says so when the player never answered', () => {
    render(<ResultPanel question={q('mcq')} reveal={null} you={null} myChoice={null} />)
    expect(screen.getByText(/You did not answer/)).toBeInTheDocument()
  })
})
