function accountId(): string {
  try {
    return String(JSON.parse(localStorage.getItem('edututor_user') || 'null')?.id ?? 'guest')
  } catch {
    return 'guest'
  }
}

export function sessionStorageKey(studentId: number): string {
  return `edututor_session:${accountId()}:${studentId}`
}

export function loadStoredSession(studentId: number): number | null {
  const value = Number(localStorage.getItem(sessionStorageKey(studentId)))
  return Number.isInteger(value) && value > 0 ? value : null
}

export function storeSession(studentId: number, sessionId: number): void {
  localStorage.setItem(sessionStorageKey(studentId), String(sessionId))
}

export function clearStoredSession(studentId: number): void {
  localStorage.removeItem(sessionStorageKey(studentId))
}
