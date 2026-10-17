import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Report } from '../../lib/types'
import {
  fmtSeconds,
  needsSupport,
  noAnswers,
  optionIndex,
  questionBadge,
  topWrongOption,
} from './format'

// react-i18next hands out a stable `t`; the mock must too, or effects that depend on it loop.
const t = (_k: string, d: string) => d
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t }) }))

const report: Report = {
  session_id: 's1',
  title: 'Cells',
  topic: 'Biology',
  overall: {
    players: 3,
    questions: 3,
    avg_score: 1133,
    accuracy_pct: 44,
    avg_response_ms: 4000,
    participation_pct: 100,
  },
  per_question: [1, 2, 3].map((n) => ({
    question_id: `q${n}`,
    position: n - 1,
    text: `Question ${n}?`,
    subtopic: n < 3 ? 'Organelles' : 'Division',
    accuracy_pct: n === 1 ? 67 : 33,
    avg_response_ms: 4000,
    answered: 3,
    distribution: { A: 1, B: 2 },
    correct_option_ids: ['B'],
  })),
  per_student: [
    {
      player_id: 'p1',
      nickname: 'ann',
      rank: 1,
      score: 2500,
      correct: 3,
      accuracy_pct: 100,
      avg_response_ms: 4000,
    },
    {
      player_id: 'p2',
      nickname: 'cy',
      rank: 2,
      score: 0,
      correct: 0,
      accuracy_pct: 0,
      avg_response_ms: 4000,
    },
  ],
  subtopics: [
    { subtopic: 'Organelles', accuracy_pct: 50, attempts: 6 },
    { subtopic: 'Division', accuracy_pct: 33, attempts: 3 },
  ],
  weak_subtopics: [{ subtopic: 'Division', accuracy_pct: 33, attempts: 3 }],
  hardest: ['q2', 'q3'],
  easiest: ['q1'],
  ai_summary: null,
}

const apiMock = vi.hoisted(() => ({
  report: vi.fn(),
  summarize: vi.fn(),
  download: vi.fn(),
}))
vi.mock('../../lib/api', async (orig) => ({
  ...(await orig<typeof import('../../lib/api')>()),
  api: apiMock,
}))

import ReportView from '../../pages/ReportView'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/teacher/reports/s1']}>
      <Routes>
        <Route path="/teacher/reports/:sessionId" element={<ReportView />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  apiMock.report.mockReset().mockResolvedValue(report)
  apiMock.summarize.mockReset()
})

describe('format helpers', () => {
  it('formats times, options and flags', () => {
    expect(fmtSeconds(4200)).toBe('4.2s')
    expect(fmtSeconds(0)).toBe('–')
    expect(optionIndex('C', 0)).toBe(2)
    expect(optionIndex('zz', 1)).toBe(1)
    expect(needsSupport(report.per_student[1])).toBe(true)
    expect(needsSupport(report.per_student[0])).toBe(false)
    const silent = { ...report.per_student[1], answered: 0 }
    expect(noAnswers(silent)).toBe(true)
    expect(needsSupport(silent)).toBe(false) // absent is not the same as struggling
    expect(questionBadge(report.per_question[1], report)).toBe('hardest')
    expect(questionBadge(report.per_question[0], report)).toBe('easiest')
  })
})

describe('ReportView', () => {
  it('shows overview, weak topics, per-question results and students', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Cells' })).toBeInTheDocument()
    expect(screen.getByText('44%')).toBeInTheDocument()
    expect(screen.getByText(/Needs review/)).toBeInTheDocument()
    expect(screen.getAllByLabelText('Correct answer')).toHaveLength(3)
    expect(screen.getByText('Needs support')).toBeInTheDocument()
    expect(screen.getAllByText(/Hardest/, { selector: 'span' })).toHaveLength(2)
  })

  it('generates an AI summary on demand and shows it', async () => {
    apiMock.summarize.mockResolvedValue({
      class_insight: 'The class struggled with division.',
      reteach: ['Mitosis phases'],
      study_tips: { Division: 'Draw the phases' },
    })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Generate AI summary' }))
    expect(await screen.findByText('The class struggled with division.')).toBeInTheDocument()
    expect(screen.getByText('Mitosis phases')).toBeInTheDocument()
    expect(screen.getByText('Draw the phases')).toBeInTheDocument()
  })

  it('keeps the report visible and shows a clear message when the AI is unavailable', async () => {
    const { ApiError } = await import('../../lib/api')
    apiMock.summarize.mockRejectedValue(
      new ApiError(503, 'The AI summary is unavailable right now.'),
    )
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Generate AI summary' }))
    await waitFor(() =>
      expect(screen.getByText('The AI summary is unavailable right now.')).toBeInTheDocument(),
    )
    expect(screen.getByRole('heading', { name: 'Cells' })).toBeInTheDocument()
  })
})

describe('topWrongOption', () => {
  const base = { correct_option_ids: ['A'], answered: 10 }
  it('finds a real pattern', () => {
    expect(topWrongOption({ ...base, distribution: { A: 4, B: 5, C: 1 } })).toEqual({
      id: 'B',
      count: 5,
    })
  })
  it('ignores one-off mistakes and spread-out guesses', () => {
    expect(topWrongOption({ ...base, distribution: { A: 8, B: 1, C: 1 } })).toBeNull()
    expect(topWrongOption({ ...base, distribution: { A: 4, B: 2, C: 2, D: 2 } })).toBeNull()
  })
})
