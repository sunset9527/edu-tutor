// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import router from './index'

describe('v1.8 learning route', () => {
  it('resolves the learning-plan workflow page', () => {
    expect(router.resolve('/learning').name).toBe('learning')
  })
})
