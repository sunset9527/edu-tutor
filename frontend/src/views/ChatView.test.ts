// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api/edu', () => ({
  eduApi: {
    listStudents: vi.fn().mockResolvedValue([]),
  },
}))

import ChatView from './ChatView.vue'

describe('ChatView', () => {
  it('renders the real memory trace panel and empty guidance', async () => {
    const wrapper = mount(ChatView, {
      global: { plugins: [createPinia(), ElementPlus] },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('本轮记忆轨迹')
    expect(wrapper.text()).toContain('发送问题后显示真实检索与写入结果')
    wrapper.unmount()
  })
})
