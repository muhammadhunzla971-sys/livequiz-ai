import type { Envelope } from '../lib/types'

export type ConnStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'

export interface SocketOptions {
  /** A function is re-evaluated on every (re)connect so a fresh auth token can be used. */
  url: string | (() => string)
  onMessage: (msg: Envelope) => void
  onStatus: (status: ConnStatus, closeCode?: number) => void
  /** Close codes after which retrying is pointless (unauthorized, kicked, not found...). */
  fatalCodes?: number[]
  WebSocketImpl?: typeof WebSocket
}

const FATAL_DEFAULT = [4401, 4403, 4404, 4409, 4410]

/**
 * Typed WebSocket with exponential-backoff reconnect and a clock-skew estimate.
 * skew = serverTime - clientTime, refined from ping/pong round trips (lowest RTT wins).
 */
export class RoomSocket {
  private ws: WebSocket | null = null
  private attempts = 0
  private stopped = false
  private timer: ReturnType<typeof setTimeout> | null = null
  private pinger: ReturnType<typeof setInterval> | null = null
  private bestRtt = Infinity
  skewMs = 0

  constructor(private opts: SocketOptions) {}

  connect(): void {
    this.stopped = false
    this.open()
  }

  private open(): void {
    const Impl = this.opts.WebSocketImpl ?? WebSocket
    this.opts.onStatus(this.attempts === 0 ? 'connecting' : 'reconnecting')
    const ws = new Impl(typeof this.opts.url === 'function' ? this.opts.url() : this.opts.url)
    this.ws = ws
    ws.onopen = () => {
      this.attempts = 0
      this.opts.onStatus('open')
      this.ping()
      this.pinger = setInterval(() => this.ping(), 10_000)
    }
    ws.onmessage = (ev) => {
      let msg: Envelope
      try {
        msg = JSON.parse(String(ev.data)) as Envelope
      } catch {
        return
      }
      if (msg.type === 'pong') this.onPong(msg)
      else this.opts.onMessage(msg)
    }
    ws.onclose = (ev) => {
      this.clearPinger()
      if (this.ws !== ws) return
      const fatal = this.opts.fatalCodes ?? FATAL_DEFAULT
      if (this.stopped || fatal.includes(ev.code)) {
        this.opts.onStatus('closed', ev.code)
        return
      }
      this.attempts += 1
      this.opts.onStatus('reconnecting', ev.code)
      const delay = Math.min(1000 * 2 ** (this.attempts - 1), 8000) + Math.random() * 300
      this.timer = setTimeout(() => this.open(), delay)
    }
    ws.onerror = () => ws.close()
  }

  private ping(): void {
    this.send('ping', { client_ts: Date.now() })
  }

  private onPong(msg: Envelope): void {
    const p = msg.payload as { client_ts?: number; server_time?: number }
    if (typeof p.client_ts !== 'number' || typeof p.server_time !== 'number') return
    const now = Date.now()
    const rtt = now - p.client_ts
    if (rtt <= this.bestRtt + 20) {
      this.bestRtt = Math.min(this.bestRtt, rtt)
      this.skewMs = p.server_time + rtt / 2 - now
    }
  }

  /** Server time as the client believes it to be right now. */
  serverNow(): number {
    return Date.now() + this.skewMs
  }

  send(type: string, payload: Record<string, unknown> = {}): boolean {
    if (!this.ws || this.ws.readyState !== 1) return false
    this.ws.send(JSON.stringify({ v: 1, type, payload }))
    return true
  }

  private clearPinger(): void {
    if (this.pinger) clearInterval(this.pinger)
    this.pinger = null
  }

  close(): void {
    this.stopped = true
    if (this.timer) clearTimeout(this.timer)
    this.clearPinger()
    this.ws?.close()
    this.ws = null
  }
}
