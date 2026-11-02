export interface StoredAuthUser {
  id: number
  username: string
  role?: string
}

export interface RouteAccessTarget {
  path: string
  requiresAdmin?: boolean
}

export function resolveRouteAccess(
  target: RouteAccessTarget,
  token: string,
  user: StoredAuthUser | null,
): true | string {
  if (target.path !== '/login' && !token) return '/login'
  if (target.path === '/login' && token) return '/chat'
  if (target.requiresAdmin && user?.role !== 'admin') return '/chat'
  return true
}

export function readStoredUser(): StoredAuthUser | null {
  try {
    return JSON.parse(localStorage.getItem('edututor_user') || 'null')
  } catch {
    return null
  }
}
