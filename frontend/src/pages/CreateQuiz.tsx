import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Button, Card, ErrorNote, Input, Select } from '../components/ui'
import { ApiError, api, generateQuizStream } from '../lib/api'
import type { GenerateRequest, Level, QuestionType } from '../lib/types'

const LANGS: [string, string][] = [
  ['en', 'English'],
  ['ur', 'اردو (Urdu)'],
  ['ar', 'العربية (Arabic)'],
  ['hi', 'हिन्दी (Hindi)'],
  ['es', 'Español'],
  ['fr', 'Français'],
]

const TYPES: [QuestionType, string][] = [
  ['mcq', 'Multiple choice'],
  ['true_false', 'True / False'],
  ['multi_select', 'Multi-select'],
]

export default function CreateQuiz() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const [step, setStep] = useState<1 | 2>(1)
  const [topic, setTopic] = useState('')
  const [level, setLevel] = useState<Level>('beginner')
  const [goal, setGoal] = useState('')
  const [count, setCount] = useState(10)
  const [types, setTypes] = useState<QuestionType[]>(['mcq', 'true_false'])
  const [seconds, setSeconds] = useState(20)
  const [language, setLanguage] = useState('en')
  const [progress, setProgress] = useState<string[]>([])
  const [generating, setGenerating] = useState(false)
  const [err, setErr] = useState('')
  const [manualBusy, setManualBusy] = useState(false)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => () => abort.current?.abort(), [])

  const step1Ok = topic.trim().length >= 2

  function toggleType(ty: QuestionType) {
    setTypes((cur) => (cur.includes(ty) ? cur.filter((x) => x !== ty) : [...cur, ty]))
  }

  async function generate(e: FormEvent) {
    e.preventDefault()
    if (types.length === 0)
      return setErr(t('create.pickType', 'Choose at least one question type.'))
    setErr('')
    setProgress([])
    setGenerating(true)
    const ctl = new AbortController()
    abort.current = ctl
    const body: GenerateRequest = {
      topic: topic.trim(),
      level,
      learning_goal: goal.trim(),
      num_questions: count,
      question_types: types,
      time_limit_sec: seconds,
      language,
    }
    try {
      const quiz = await generateQuizStream(
        body,
        (m) => setProgress((p) => (p[p.length - 1] === m ? p : [...p, m])),
        ctl.signal,
      )
      nav(`/teacher/quiz/${quiz.id}`)
    } catch (ex) {
      if (ctl.signal.aborted) return
      setGenerating(false)
      if (ex instanceof ApiError && ex.status === 429)
        setErr(
          t(
            'create.rate',
            'You have reached the hourly generation limit. Try again later or build the quiz by hand.',
          ),
        )
      else if (ex instanceof ApiError && ex.status === 422)
        setErr(
          ex.message || t('create.rejected', 'That topic could not be used. Try rewording it.'),
        )
      else if (ex instanceof ApiError) setErr(ex.message)
      else setErr(t('err.generic', 'Something went wrong. Try again.'))
    }
  }

  async function manual() {
    setManualBusy(true)
    try {
      const quiz = await api.createQuiz({
        title: topic.trim() || 'Untitled quiz',
        topic: topic.trim() || 'General',
        level,
        learning_goal: goal.trim(),
        language,
        questions: [],
        tags: [],
      })
      nav(`/teacher/quiz/${quiz.id}`)
    } catch (ex) {
      setErr(
        ex instanceof ApiError ? ex.message : t('err.generic', 'Something went wrong. Try again.'),
      )
      setManualBusy(false)
    }
  }

  if (generating)
    return (
      <Card className="mx-auto mt-8 max-w-xl">
        <h1 className="text-3xl font-extrabold">{t('create.working', 'Building your quiz…')}</h1>
        <p className="mt-1 text-muted">{topic}</p>
        <ul className="mt-5 space-y-2" aria-live="polite">
          {progress.map((m, i) => (
            <li key={`${i}-${m}`} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={i === progress.length - 1 ? 'animate-pulse' : 'text-good'}
              >
                {i === progress.length - 1 ? '●' : '✓'}
              </span>
              {m}
            </li>
          ))}
          {progress.length === 0 && (
            <li className="text-muted">{t('create.starting', 'Starting…')}</li>
          )}
        </ul>
        <Button
          variant="ghost"
          className="mt-6"
          onClick={() => {
            abort.current?.abort()
            setGenerating(false)
          }}
        >
          {t('common.cancel', 'Cancel')}
        </Button>
      </Card>
    )

  return (
    <div className="mx-auto max-w-2xl pt-4">
      <h1 className="text-4xl font-extrabold">{t('create.title', 'Create a quiz')}</h1>
      <ol className="mt-4 flex gap-2" aria-label="Steps">
        {[t('create.s1', 'Topic'), t('create.s2', 'Settings')].map((label, i) => (
          <li
            key={label}
            aria-current={step === i + 1 ? 'step' : undefined}
            className={`rounded-full px-4 py-1 text-sm font-bold ${step === i + 1 ? 'bg-ink text-paper' : 'border border-line text-muted'}`}
          >
            {i + 1}. {label}
          </li>
        ))}
      </ol>

      <Card className="mt-5">
        <form
          onSubmit={step === 1 ? (e) => (e.preventDefault(), step1Ok && setStep(2)) : generate}
          className="space-y-5"
        >
          {step === 1 ? (
            <>
              <Input
                label={t('create.topic', 'Topic')}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                maxLength={300}
                placeholder="Photosynthesis"
                required
                autoFocus
              />
              <Select
                label={t('create.level', 'Level')}
                value={level}
                onChange={(e) => setLevel(e.target.value as Level)}
              >
                <option value="beginner">Beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </Select>
              <label className="block">
                <span className="mb-1 block text-sm font-bold">
                  {t('create.goal', 'Learning goal')}
                </span>
                <textarea
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  maxLength={1000}
                  rows={3}
                  placeholder="Students should understand the inputs and outputs of photosynthesis."
                  className="w-full rounded-xl border border-line bg-card px-4 py-3"
                />
                <span className="mt-1 block text-sm text-muted">
                  {t(
                    'create.goalHint',
                    'Optional, but it makes the questions much more on target.',
                  )}
                </span>
              </label>
              <ErrorNote>{err}</ErrorNote>
              <div className="flex flex-wrap gap-3">
                <Button type="submit" disabled={!step1Ok}>
                  {t('common.next', 'Next')}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  busy={manualBusy}
                  onClick={() => void manual()}
                >
                  {t('create.manual', 'Build it by hand instead')}
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <Input
                  label={t('create.count', 'Number of questions')}
                  type="number"
                  min={5}
                  max={30}
                  value={count}
                  onChange={(e) => setCount(Math.min(30, Math.max(5, Number(e.target.value) || 5)))}
                  hint="5 to 30"
                />
                <Input
                  label={t('create.time', 'Seconds per question')}
                  type="number"
                  min={5}
                  max={120}
                  value={seconds}
                  onChange={(e) =>
                    setSeconds(Math.min(120, Math.max(5, Number(e.target.value) || 20)))
                  }
                />
              </div>
              <Select
                label={t('create.lang', 'Language')}
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {LANGS.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </Select>
              <fieldset>
                <legend className="mb-1 text-sm font-bold">
                  {t('create.types', 'Question types')}
                </legend>
                <div className="flex flex-wrap gap-2">
                  {TYPES.map(([ty, label]) => (
                    <label
                      key={ty}
                      className={`flex min-h-[44px] cursor-pointer items-center gap-2 rounded-xl border px-4 ${types.includes(ty) ? 'border-ink bg-signal/30' : 'border-line'}`}
                    >
                      <input
                        type="checkbox"
                        checked={types.includes(ty)}
                        onChange={() => toggleType(ty)}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </fieldset>
              <ErrorNote>{err}</ErrorNote>
              {err && (
                <Button
                  type="button"
                  variant="ghost"
                  busy={manualBusy}
                  onClick={() => void manual()}
                >
                  {t('create.manual', 'Build it by hand instead')}
                </Button>
              )}
              <div className="flex flex-wrap gap-3">
                <Button type="button" variant="ghost" onClick={() => setStep(1)}>
                  {t('common.back', 'Back')}
                </Button>
                <Button type="submit" variant="signal">
                  {t('create.generate', 'Generate quiz')}
                </Button>
              </div>
            </>
          )}
        </form>
      </Card>
    </div>
  )
}
