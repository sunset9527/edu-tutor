// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listStudents: vi.fn().mockResolvedValue([{ id: 1, name: '小明' }]),
  getGraph: vi.fn().mockResolvedValue({ nodes: [{ id: 10, title: '长度单位' }], edges: [] }),
  getLearningGoal: vi.fn().mockResolvedValue({ id: 9, student_id: 1, current_version: { id: 2, version_no: 1, target_date: '2026-12-31', weekly_minutes: 120, subject: '数学', target_level: '熟练', status: 'active', change_reason: 'created', target_knowledge_point_ids: [10] } }),
  getLatestDiagnostic: vi.fn().mockRejectedValue(new Error('none')),
  getLearningPlanHistory: vi.fn().mockResolvedValue({ plans: [] }),
}))

vi.mock('../api/edu', () => ({ eduApi: api }))

import LearningPlanView from './LearningPlanView.vue'

describe('LearningPlanView', () => {
  it('offers an editable versioned goal form for an existing goal', async () => {
    const wrapper = mount(LearningPlanView, { global: { plugins: [ElementPlus] } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('编辑目标')
    wrapper.unmount()
  })
})
