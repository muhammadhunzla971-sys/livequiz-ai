import { motion } from 'framer-motion'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ANSWER_STYLES, Shape } from '../../components/Shapes'
import { Button, cx } from '../../components/ui'
import type { PublicQuestion } from '../../lib/types'

interface Props {
  question: PublicQuestion
  /** The answer already sent for this question (null = not answered yet). */
  chosen: string[] | null
  /** True while the game is paused or the socket is not usable. */
  disabled: boolean
  onSubmit: (ids: string[]) => void
}

/**
 * The student's answer buttons. Single choice: one tap sends the answer (the first answer wins on
 * the server, so we lock straight away). Multi select: toggle options, then lock in.
 * Keys 1-5 pick an option on a keyboard.
 */
export default function AnswerPad({ question, chosen, disabled, onSubmit }: Props) {
  const { t } = useTranslation()
  const multi = question.type === 'multi_select'
  const [sel, setSel] = useState<string[]>([])
  const locked = chosen !== null
  const shown = chosen ?? sel

  useEffect(() => setSel([]), [question.question_id])

  const pick = useCallback(
    (id: string) => {
      if (locked || disabled) return
      if (multi) setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
      else onSubmit([id])
    },
    [locked, disabled, multi, onSubmit],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= question.options.length) pick(question.options[n - 1].id)
      else if (e.key === 'Enter' && multi && !locked && !disabled && sel.length > 0) onSubmit(sel)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [question.options, pick, multi, locked, disabled, sel, onSubmit])

  return (
    <div className="space-y-4">
      {multi && !locked && (
        <p className="font-bold text-muted">
          {t('play.multiHint', 'Select all the correct answers, then lock in.')}
        </p>
      )}
      <ul className="grid gap-3 sm:grid-cols-2">
        {question.options.map((o, i) => {
          const style = ANSWER_STYLES[i]
          const on = shown.includes(o.id)
          return (
            <li key={o.id}>
              <motion.button
                type="button"
                whileTap={locked || disabled ? undefined : { scale: 0.97 }}
                onClick={() => pick(o.id)}
                aria-pressed={on}
                disabled={disabled && !locked}
                className={cx(
                  'flex min-h-[72px] w-full items-center gap-4 rounded-2xl p-4 text-start text-xl font-bold text-white transition',
                  style.bg,
                  locked && !on && 'opacity-35',
                  on && 'ring-4 ring-ink ring-offset-2 ring-offset-paper',
                  disabled && !locked && 'opacity-60',
                )}
              >
                <Shape name={style.shape} className="h-8 w-8 shrink-0" />
                <span className="min-w-0 flex-1 break-words">{o.text}</span>
                {on && (
                  <span aria-hidden="true" className="text-2xl">
                    ✓
                  </span>
                )}
              </motion.button>
            </li>
          )
        })}
      </ul>

      {multi && !locked && (
        <Button
          big
          variant="signal"
          className="w-full"
          disabled={sel.length === 0 || disabled}
          onClick={() => onSubmit(sel)}
        >
          {t('play.lockIn', 'Lock in answer')}
        </Button>
      )}
    </div>
  )
}
