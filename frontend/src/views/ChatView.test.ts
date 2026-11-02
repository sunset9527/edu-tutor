// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listStudents: vi.fn(),
  getMemories: vi.fn(),
  getSessionMessages: vi.fn(),
  endSession: vi.fn(),
  recordWrongQuestion: vi.fn(),
  confirmReviewPlan: vi.fn(),
  submitCorrection: vi.fn(),
}))
const stream = vi.hoisted(() => vi.fn())

vi.mock('../api/edu', () => ({ eduApi: api }))
vi.mock('../api/sse', () => ({ streamChat: stream }))

import ChatView from './ChatView.vue'

describe('ChatView', () => {
  beforeEach(() => {
    localStorage.clear()
    api.listStudents.mockResolvedValue([])
    api.getMemories.mockResolvedValue({ total: 0, items: [] })
    api.getSessionMessages.mockResolvedValue({ student_id: 1, messages: [] })
  })

  it('renders the real memory trace panel and empty guidance', async () => {
    const wrapper = mount(ChatView, {
      global: { plugins: [createPinia(), ElementPlus] },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('本轮记忆轨迹')
    expect(wrapper.text()).toContain('发送问题后显示真实检索与写入结果')
    wrapper.unmount()
  })

  it('renders streamed textbook evidence and binds feedback to the assistant message', async () => {
    api.listStudents.mockResolvedValue([
      { id: 1, name: '小明', grade: '七年级', subject: '数学', level: '基础' },
    ])
    stream.mockImplementation(async (_payload, onEvent) => {
      onEvent({
        event: 'knowledge_retrieved',
        data: {
          candidates: [{ knowledge_point_id: 8, title: '一元一次方程', textbook: '数学七上', version_no: 2, page_range: [3, 4], similarity: 0.91, adopted: true, provenance_gap: false }],
          evidence_gap: { evidence_gap: false },
        },
      })
      onEvent({ event: 'response_chunk', data: { text: '先移项，再合并同类项。' } })
      onEvent({ event: 'evidence_recorded', data: { assistant_message_id: 99, evidence_ledger_id: 20, evidence_gap: { evidence_gap: false } } })
      onEvent({ event: 'completed', data: { evidence: { knowledge: [], gap: { evidence_gap: false } } } })
      return 6
    })
    const wrapper = mount(ChatView, { global: { plugins: [createPinia(), ElementPlus] } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    const textarea = wrapper.find('textarea')
    await textarea.setValue('方程怎么解？')
    const sendButton = wrapper.findAll('button').find((button) => button.text() === '发送')
    await sendButton?.trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(wrapper.text()).toContain('本轮教材证据')
    expect(wrapper.text()).toContain('一元一次方程')
    expect(wrapper.text()).toContain('第 3-4 页')
    expect(wrapper.text()).toContain('反馈此回答')
    expect(wrapper.text()).toContain('消息 #99')
    wrapper.unmount()
  })
})
