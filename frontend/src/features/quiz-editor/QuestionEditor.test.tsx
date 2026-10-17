import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import QuestionEditor from './QuestionEditor'
import { type EditableQuestion, newQuestion } from './model'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, d: string) => d }),
}))

function Harness({
  onDelete = () => {},
  regen,
}: {
  onDelete?: () => void
  regen?: (f: string) => void
}) {
  const [q, setQ] = useState<EditableQuestion>(newQuestion('mcq'))
  return (
    <ul>
      <QuestionEditor
        q={q}
        index={0}
        total={1}
        defaultOpen
        onChange={setQ}
        onMove={() => {}}
        onDelete={onDelete}
        onRegenerate={regen}
      />
    </ul>
  )
}

describe('QuestionEditor', () => {
  it('shows problems for an empty question and clears them as it is filled in', () => {
    render(<Harness />)
    expect(screen.getByRole('alert')).toHaveTextContent(/at least 5/)
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Which gas do plants absorb?' },
    })
    for (const id of ['A', 'B', 'C', 'D'])
      fireEvent.change(screen.getByLabelText(`Option ${id}`), { target: { value: `Answer ${id}` } })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('adds an option up to the maximum of five', () => {
    render(<Harness />)
    fireEvent.click(screen.getByText(/Add option/))
    expect(screen.getByLabelText('Option E')).toBeInTheDocument()
    expect(screen.queryByText(/Add option/)).toBeNull()
  })

  it('asks before deleting', () => {
    const onDelete = vi.fn()
    render(<Harness onDelete={onDelete} />)
    fireEvent.click(screen.getByText('Delete'))
    expect(onDelete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Yes, delete'))
    expect(onDelete).toHaveBeenCalledOnce()
  })

  it('disables regenerate for a question that has not been saved yet', () => {
    render(<Harness />)
    expect(screen.getByText(/Regenerate with AI/).closest('button')).toBeDisabled()
  })

  it('sends regenerate feedback', () => {
    const regen = vi.fn()
    render(<Harness regen={regen} />)
    fireEvent.click(screen.getByText(/Regenerate with AI/))
    fireEvent.change(screen.getByPlaceholderText(/Make it harder/), { target: { value: 'harder' } })
    fireEvent.click(screen.getByText('Regenerate'))
    expect(regen).toHaveBeenCalledWith('harder')
  })
})
