import { beforeEach, describe, expect, it } from 'vitest'
import { deviceId } from './device'

describe('deviceId', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('is stable within a tab so a refresh rejoins as the same player', () => {
    expect(deviceId()).toBe(deviceId())
  })

  it('is per tab: a different tab (empty sessionStorage) gets a different id, even if localStorage is shared', () => {
    localStorage.setItem('lq.device', 'shared-by-all-incognito-windows')
    const first = deviceId()
    sessionStorage.clear() // simulates opening the game in another tab or window
    const second = deviceId()
    expect(second).not.toBe(first)
    expect(second).not.toBe('shared-by-all-incognito-windows')
  })
})
