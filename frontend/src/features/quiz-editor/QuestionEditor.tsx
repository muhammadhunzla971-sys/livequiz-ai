import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ANSWER_STYLES, Shape } from '../../components/Shapes'
import { Button, cx } from '../../components/ui'
import {
  type EditableQuestion,
  addOption,
  maxOptions,
  minOptions,
  removeOption,
  setCorrect,
  setOptionText,
  validateQuestion,
} from './model'

const TYPE_LABEL = {
  mcq: 'Multiple choice',
  true_false: 'True / False',
  multi_select: 'Multi-select',
}

interface Props {
  q: EditableQuestion
  index: number
  total: number
  defaultOpen?: boolean
  busy?: boolean
  onChange: (q: EditableQuestion) => void
  onMove: (dir: -1 | 1) => void
  onDelete: () => void
  /** Undefined when the question has not been saved yet (the server needs its id). */
  onRegenerate?: (feedback: string) => void
}

export default function QuestionEditor({
  q,
  index,
  total,
  defaultOpen,
  busy,
  onChange,
  onMove,
  onDelete,
  onRegenerate,
}: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(!!defaultOpen)
  const [regen, setRegen] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const issues = validateQuestion(q)
  const multi = q.type === 'multi_select'
  const field = 'w-full rounded-xl border border-line bg-card px-3 py-2'

  return (
    <li
      className={cx('rounded-2xl border bg-card', issues.length ? 'border-bad/60' : 'border-line')}
    >
      <div className="flex items-center gap-3 p-3">
        <button
          className="flex min-h-[44px] flex-1 items-center gap-3 text-start"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <span className="tabular grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-ink font-display font-extrabold text-paper">
            {index + 1}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-bold">
              {q.text.trim() || t('edit.untitledQ', '(empty question)')}
            </span>
            <span className="text-sm text-muted">
              {TYPE_LABEL[q.type]} · {q.time_limit_sec}s · {q.points} pts
              {issues.length > 0 && (
                <span className="font-bold text-bad"> · {issues.length} to fix</span>
              )}
            </span>
          </span>
          <span aria-hidden="true">{open ? '▲' : '▼'}</span>
        </button>
      </div>

      {open && (
        <div className="space-y-4 border-t border-line p-4">
          <label className="block">
            <span className="mb-1 block text-sm font-bold">{t('edit.qtext', 'Question')}</span>
            <textarea
              value={q.text}
              rows={2}
              maxLength={500}
              onChange={(e) => onChange({ ...q, text: e.target.value })}
              className={field}
            />
          </label>

          <fieldset>
            <legend className="mb-1 text-sm font-bold">
              {multi
                ? t('edit.optsMulti', 'Options (tick every correct answer)')
                : t('edit.opts', 'Options (select the correct answer)')}
            </legend>
            <ul className="space-y-2">
              {q.options.map((o, i) => {
                const correct = q.correct_option_ids.includes(o.id)
                const style = ANSWER_STYLES[i]
                return (
                  <li key={o.id} className="flex items-center gap-2">
                    <span
                      className={cx(
                        'grid h-11 w-11 shrink-0 place-items-center rounded-lg text-white',
                        style.bg,
                      )}
                      aria-hidden="true"
                    >
                      <Shape name={style.shape} className="h-5 w-5" />
                    </span>
                    <input
                      aria-label={`Option ${o.id}`}
                      value={o.text}
                      maxLength={200}
                      readOnly={q.type === 'true_false'}
                      onChange={(e) => onChange(setOptionText(q, i, e.target.value))}
                      className={cx(field, 'min-h-[44px] flex-1')}
                    />
                    <label className="flex min-h-[44px] min-w-[44px] cursor-pointer items-center justify-center gap-1 rounded-lg border border-line px-2 text-sm font-bold">
                      <input
                        type={multi ? 'checkbox' : 'radio'}
                        name={`correct-${q.key}`}
                        checked={correct}
                        onChange={(e) => onChange(setCorrect(q, o.id, e.target.checked))}
                      />
                      {t('edit.correct', 'Correct')}
                    </label>
                    {q.type !== 'true_false' && (
                      <button
                        className="min-h-[44px] min-w-[44px] rounded-lg border border-line text-lg hover:bg-ink/5 disabled:opacity-40"
                        aria-label={`Remove option ${o.id}`}
                        disabled={q.options.length <= minOptions(q.type)}
                        onClick={() => onChange(removeOption(q, i))}
                      >
                        ✕
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
            {q.options.length < maxOptions(q.type) && q.type !== 'true_false' && (
              <Button variant="ghost" className="mt-2" onClick={() => onChange(addOption(q))}>
                + {t('edit.addOption', 'Add option')}
              </Button>
            )}
          </fieldset>

          <label className="block">
            <span className="mb-1 block text-sm font-bold">
              {t('edit.explain', 'Explanation (shown after the answer)')}
            </span>
            <textarea
              value={q.explanation}
              rows={2}
              maxLength={600}
              onChange={(e) => onChange({ ...q, explanation: e.target.value })}
              className={field}
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block">
              <span className="mb-1 block text-sm font-bold">
                {t('edit.time', 'Time (seconds)')}
              </span>
              <input
                type="number"
                min={5}
                max={120}
                value={q.time_limit_sec}
                onChange={(e) => onChange({ ...q, time_limit_sec: Number(e.target.value) })}
                className={field}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-bold">{t('edit.points', 'Points')}</span>
              <input
                type="number"
                min={0}
                max={10000}
                step={100}
                value={q.points}
                onChange={(e) => onChange({ ...q, points: Number(e.target.value) })}
                className={field}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-sm font-bold">{t('edit.subtopic', 'Subtopic')}</span>
              <input
                value={q.subtopic}
                maxLength={200}
                onChange={(e) => onChange({ ...q, subtopic: e.target.value })}
                className={field}
              />
            </label>
          </div>

          {issues.length > 0 && (
            <ul role="alert" className="list-disc rounded-xl bg-bad/10 py-2 ps-8 pe-3 text-bad">
              {issues.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}

          {regen && onRegenerate && (
            <div className="flex flex-wrap items-end gap-2 rounded-xl border border-line p-3">
              <label className="min-w-[200px] flex-1">
                <span className="mb-1 block text-sm font-bold">
                  {t('edit.regenHint', 'What should change? (optional)')}
                </span>
                <input
                  value={feedback}
                  maxLength={300}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="Make it harder / use a real-life example"
                  className={field}
                />
              </label>
              <Button
                variant="signal"
                busy={busy}
                onClick={() => {
                  onRegenerate(feedback)
                  setRegen(false)
                  setFeedback('')
                }}
              >
                {t('edit.regenGo', 'Regenerate')}
              </Button>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button
              variant="ghost"
              disabled={index === 0}
              onClick={() => onMove(-1)}
              aria-label="Move up"
            >
              ↑
            </Button>
            <Button
              variant="ghost"
              disabled={index === total - 1}
              onClick={() => onMove(1)}
              aria-label="Move down"
            >
              ↓
            </Button>
            <Button
              variant="ghost"
              disabled={!onRegenerate || busy}
              title={onRegenerate ? undefined : t('edit.saveFirst', 'Save the quiz first')}
              onClick={() => setRegen(!regen)}
            >
              ✨ {t('edit.regen', 'Regenerate with AI')}
            </Button>
            {confirmDelete ? (
              <>
                <Button variant="danger" onClick={onDelete}>
                  {t('dash.confirmDelete', 'Yes, delete')}
                </Button>
                <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
                  {t('common.cancel', 'Cancel')}
                </Button>
              </>
            ) : (
              <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
                {t('dash.delete', 'Delete')}
              </Button>
            )}
          </div>
        </div>
      )}
    </li>
  )
}
