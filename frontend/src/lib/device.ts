let memoryId: string | null = null

/**
 * Anonymous per-tab id so a refresh rejoins as the same player. Not personal data.
 * It lives in sessionStorage (one per tab), not localStorage: browser windows such as Chrome
 * Incognito share localStorage, which made two students on one computer count as one player.
 */
export function deviceId(): string {
  try {
    let id = sessionStorage.getItem('lq.device')
    if (!id) {
      id = crypto.randomUUID()
      sessionStorage.setItem('lq.device', id)
    }
    return id
  } catch {
    memoryId ??= crypto.randomUUID()
    return memoryId
  }
}

export interface StoredPlayer {
  room_id: string
  player_id: string
  player_token: string
  nickname: string
  avatar?: string
}

export const playerStore = {
  get(): StoredPlayer | null {
    try {
      return JSON.parse(sessionStorage.getItem('lq.player') ?? 'null')
    } catch {
      return null
    }
  },
  set(p: StoredPlayer | null): void {
    try {
      if (p) sessionStorage.setItem('lq.player', JSON.stringify(p))
      else sessionStorage.removeItem('lq.player')
    } catch {
      /* ignore */
    }
  },
}
