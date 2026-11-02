// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'

import { resolveRouteAccess } from './adminAccess'

describe('resolveRouteAccess', () => {
  it('redirects anonymous users to login', () => {
    expect(resolveRouteAccess({ path: '/admin/knowledge', requiresAdmin: true }, '', null)).toBe(
      '/login',
    )
  })

  it('keeps ordinary users out of the governance route', () => {
    expect(
      resolveRouteAccess(
        { path: '/admin/knowledge', requiresAdmin: true },
        'token',
        { id: 1, username: 'student', role: 'user' },
      ),
    ).toBe('/chat')
  })

  it('allows administrators into the governance route', () => {
    expect(
      resolveRouteAccess(
        { path: '/admin/knowledge', requiresAdmin: true },
        'token',
        { id: 2, username: 'admin', role: 'admin' },
      ),
    ).toBe(true)
  })
})
