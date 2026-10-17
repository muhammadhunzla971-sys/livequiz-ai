import type { FinalMe } from './types'

/** Draws a shareable 1080x1080 result card and triggers a PNG download. */
export function downloadResultCard(me: FinalMe, title: string): void {
  const c = document.createElement('canvas')
  c.width = c.height = 1080
  const g = c.getContext('2d')
  if (!g) return
  g.fillStyle = '#0f1b33'
  g.fillRect(0, 0, 1080, 1080)
  g.fillStyle = '#ffc93c'
  g.beginPath()
  g.moveTo(540, 140)
  g.lineTo(700, 420)
  g.lineTo(380, 420)
  g.closePath()
  g.fill()
  g.fillStyle = '#eef2fa'
  g.textAlign = 'center'
  g.font = '700 64px system-ui, sans-serif'
  g.fillText(me.nickname, 540, 560)
  g.font = '800 200px system-ui, sans-serif'
  g.fillStyle = '#ffc93c'
  g.fillText(me.rank ? `#${me.rank}` : '-', 540, 760)
  g.fillStyle = '#eef2fa'
  g.font = '500 48px system-ui, sans-serif'
  g.fillText(`${me.score.toLocaleString()} points · ${me.accuracy_pct}% correct`, 540, 850)
  g.font = '500 40px system-ui, sans-serif'
  g.fillStyle = '#98a5be'
  g.fillText(title.slice(0, 40), 540, 940)
  g.fillText('LiveQuiz', 540, 1010)
  const a = document.createElement('a')
  a.href = c.toDataURL('image/png')
  a.download = 'my-quiz-result.png'
  a.click()
}
