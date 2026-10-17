import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../../components/ui'
import type { RoomPhase } from '../../lib/types'

interface Props {
  phase: RoomPhase
  revealed: boolean
  isLast: boolean
  send: (type: string, payload?: Record<string, unknown>) => void
}

/** Bottom control bar for everything after the lobby. */
export default function Controls({ phase, revealed, isLast, send }: Props) {
  const { t } = useTranslation()
  const [confirmEnd, setConfirmEnd] = useState(false)

  const end = confirmEnd ? (
    <>
      <Button variant="danger" onClick={() => (send('host.end'), setConfirmEnd(false))}>
        {t('host.endYes', 'Yes, end the game')}
      </Button>
      <Button variant="ghost" onClick={() => setConfirmEnd(false)}>
        {t('common.cancel', 'Cancel')}
      </Button>
    </>
  ) : (
    <Button variant="ghost" onClick={() => setConfirmEnd(true)}>
      {t('host.end', 'End game')}
    </Button>
  )

  let main: React.ReactNode = null
  if (phase === 'question_active') {
    main = (
      <>
        <Button variant="ghost" onClick={() => send('host.pause')}>
          ⏸ {t('host.pause', 'Pause')}
        </Button>
        <Button variant="signal" onClick={() => send('host.skip')}>
          {t('host.closeQ', 'End question now')}
        </Button>
      </>
    )
  } else if (phase === 'paused') {
    main = (
      <Button variant="signal" onClick={() => send('host.resume')}>
        ▶ {t('host.resume', 'Resume')}
      </Button>
    )
  } else if (phase === 'question_closed') {
    main = revealed ? (
      <Button variant="signal" onClick={() => send('host.next')}>
        {t('host.showLb', 'Show leaderboard')}
      </Button>
    ) : (
      <Button variant="signal" onClick={() => send('host.reveal')}>
        {t('host.reveal', 'Reveal answer')}
      </Button>
    )
  } else if (phase === 'leaderboard') {
    main = (
      <Button variant="signal" big onClick={() => send('host.next')}>
        {isLast ? t('host.finish', 'Finish game') : t('host.next', 'Next question')}
      </Button>
    )
  }

  return (
    <div className="sticky bottom-0 -mx-4 border-t border-line bg-paper/95 px-4 py-3 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
        {main}
        <span className="flex-1" />
        {end}
      </div>
    </div>
  )
}
