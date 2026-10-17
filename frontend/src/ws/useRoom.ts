import { useEffect, useRef } from 'react'
import { wsBase } from '../lib/config'
import { useGame } from '../store/game'
import { RoomSocket } from './client'

/**
 * Opens a socket while mounted and feeds every server event into the game store.
 * `key` identifies the connection (change it to force a reconnect); `getUrl` is evaluated on
 * every (re)connect so it can read a freshly refreshed auth token.
 */
export function useRoom(role: 'host' | 'player', key: string | null, getUrl: () => string) {
  const ref = useRef<RoomSocket | null>(null)
  const urlRef = useRef(getUrl)
  urlRef.current = getUrl
  useEffect(() => {
    if (!key) return
    const { reset, apply, setConn } = useGame.getState()
    reset(role)
    const sock = new RoomSocket({
      url: () => urlRef.current(),
      onMessage: apply,
      onStatus: (s, code) => setConn(s, code),
    })
    ref.current = sock
    sock.connect()
    return () => {
      sock.close()
      ref.current = null
    }
  }, [role, key])
  return ref
}

export function wsUrl(path: string, token: string): string {
  return `${wsBase()}${path}?token=${encodeURIComponent(token)}`
}
