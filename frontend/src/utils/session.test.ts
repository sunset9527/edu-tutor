// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearStoredSession,
  loadStoredSession,
  sessionStorageKey,
  storeSession,
} from './session'

describe('student session persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('edututor_user', JSON.stringify({ id: 18 }))
  })

  it('isolates sessions by account and student', () => {
    storeSession(3, 101)
    storeSession(4, 202)
    expect(sessionStorageKey(3)).toBe('edututor_session:18:3')
    expect(loadStoredSession(3)).toBe(101)
    expect(loadStoredSession(4)).toBe(202)
  })

  it('clears only the selected student session', () => {
    storeSession(3, 101)
    storeSession(4, 202)
    clearStoredSession(3)
    expect(loadStoredSession(3)).toBeNull()
    expect(loadStoredSession(4)).toBe(202)
  })
})
