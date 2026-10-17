import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Shell } from '../components/Chrome'
import { Button, Card, ErrorNote, Input, Spinner } from '../components/ui'
import { ApiError, api } from '../lib/api'
import { deviceId, playerStore } from '../lib/device'

const AVATARS = ['🦊', '🐼', '🦁', '🐙', '🦄', '🐸', '🐧', '🦉', '🐢', '🚀', '⭐', '🎨']

export default function Join() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const pin = params.get('pin') ?? ''
  const [title, setTitle] = useState<string | null>(null)
  const [fatal, setFatal] = useState('')
  const [nick, setNick] = useState('')
  const [avatar, setAvatar] = useState(AVATARS[0])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!/^\d{6}$/.test(pin)) return setFatal(t('join.badPin', 'That link has no valid game PIN.'))
    api
      .lookupPin(pin)
      .then((r) => {
        setTitle(r.title)
        if (r.locked) setFatal(t('join.locked', 'The teacher has locked this game.'))
      })
      .catch((ex) =>
        setFatal(
          ex instanceof ApiError && ex.status === 404
            ? t('join.gone', 'This game was not found. It may have ended.')
            : t('err.generic', 'Something went wrong. Try again.'),
        ),
      )
  }, [pin, t])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      const r = await api.join(pin, nick.trim(), avatar, deviceId())
      playerStore.set({ ...r, avatar })
      nav('/play')
    } catch (ex) {
      if (ex instanceof ApiError) {
        const map: Record<string, string> = {
          nickname_taken: t('join.taken', 'Someone already uses that nickname. Try another.'),
          not_open: t(
            'join.notOpen',
            'The teacher has not opened the lobby yet. Try again in a moment.',
          ),
          locked: t('join.locked', 'The teacher has locked this game.'),
          full: t('join.full', 'This game is full.'),
          nickname_banned: t('join.banned', 'That nickname is not available.'),
        }
        setErr(map[ex.code ?? ''] ?? ex.message)
      } else setErr(t('err.generic', 'Something went wrong. Try again.'))
    } finally {
      setBusy(false)
    }
  }

  if (fatal)
    return (
      <Shell>
        <Card className="mt-8 text-center">
          <h1 className="text-3xl font-extrabold">{t('join.cannot', 'Can’t join this game')}</h1>
          <p className="mt-3 text-muted">{fatal}</p>
          <Button className="mt-6" onClick={() => nav('/')}>
            {t('join.tryPin', 'Enter a different PIN')}
          </Button>
        </Card>
      </Shell>
    )

  return (
    <Shell>
      <Card className="mx-auto mt-8 max-w-md">
        {title === null ? (
          <div className="grid place-items-center py-10">
            <Spinner />
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-5">
            <div>
              <p className="text-muted">{t('join.joining', 'Joining')}</p>
              <h1 className="text-3xl font-extrabold">{title}</h1>
            </div>
            <Input
              label={t('join.nickname', 'Your nickname')}
              value={nick}
              onChange={(e) => setNick(e.target.value)}
              maxLength={20}
              required
              autoFocus
              autoComplete="off"
              hint={t('join.nickHint', 'Other players will see this.')}
            />
            <fieldset>
              <legend className="mb-1 text-sm font-bold">
                {t('join.avatar', 'Pick an emoji')}
              </legend>
              <div className="grid grid-cols-6 gap-2">
                {AVATARS.map((a) => (
                  <button
                    type="button"
                    key={a}
                    aria-pressed={avatar === a}
                    onClick={() => setAvatar(a)}
                    className={`grid h-12 place-items-center rounded-xl border text-2xl ${avatar === a ? 'border-ink bg-signal/40' : 'border-line bg-card'}`}
                  >
                    <span aria-hidden="true">{a}</span>
                    <span className="sr-only">{a}</span>
                  </button>
                ))}
              </div>
            </fieldset>
            <ErrorNote>{err}</ErrorNote>
            <Button type="submit" variant="signal" big busy={busy} className="w-full">
              {t('join.go', 'Join')}
            </Button>
          </form>
        )}
      </Card>
    </Shell>
  )
}
