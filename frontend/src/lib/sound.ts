// Tiny WebAudio blips so there are no asset downloads. Mute state is a per-viewer preference.
let ctx: AudioContext | null = null
let muted = (() => {
  try {
    return localStorage.getItem('lq.muted') === '1'
  } catch {
    return false
  }
})()

export const sound = {
  isMuted: () => muted,
  setMuted(v: boolean) {
    muted = v
    try {
      localStorage.setItem('lq.muted', v ? '1' : '0')
    } catch {
      /* ignore */
    }
  },
  play(kind: 'tick' | 'good' | 'bad' | 'start' | 'win') {
    if (muted || typeof AudioContext === 'undefined') return
    ctx ??= new AudioContext()
    const notes: Record<string, number[]> = {
      tick: [660],
      good: [523, 784],
      bad: [196, 164],
      start: [392, 523, 659],
      win: [523, 659, 784, 1047],
    }
    notes[kind].forEach((freq, i) => {
      const osc = ctx!.createOscillator()
      const gain = ctx!.createGain()
      osc.frequency.value = freq
      osc.type = 'triangle'
      const t = ctx!.currentTime + i * 0.12
      gain.gain.setValueAtTime(0.0001, t)
      gain.gain.exponentialRampToValueAtTime(0.15, t + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.2)
      osc.connect(gain).connect(ctx!.destination)
      osc.start(t)
      osc.stop(t + 0.22)
    })
  },
}
