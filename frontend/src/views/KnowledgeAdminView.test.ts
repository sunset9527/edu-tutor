// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listTextbooks: vi.fn(),
  listBuilds: vi.fn(),
  listCorrections: vi.fn(),
}))

vi.mock('../api/governance', () => ({ governanceApi: api }))

import KnowledgeAdminView from './KnowledgeAdminView.vue'

describe('KnowledgeAdminView', () => {
  beforeEach(() => {
    api.listTextbooks.mockResolvedValue({
      items: [
        {
          id: 11,
          subject: '数学',
          grade: '七年级',
          publisher: '示例出版社',
          edition: '2026',
          volume: '上册',
          file_sha256: 'abc123',
          active_version_id: 7,
        },
      ],
      total: 1,
    })
    api.listBuilds.mockResolvedValue({
      items: [
        {
          id: 21,
          textbook_id: 11,
          target_version_id: 8,
          status: 'needs_attention',
          stage: 'extracting',
          total_units: 10,
          completed_units: 6,
          failed_units: 1,
        },
      ],
      total: 1,
    })
    api.listCorrections.mockResolvedValue({
      items: [
        {
          id: 31,
          category: 'knowledge',
          status: 'pending',
          reason: '正文有误',
          original_value: {},
          proposed_value: { content_md: '建议正文' },
        },
      ],
      total: 1,
    })
  })

  it('renders four governance workspaces and real summary data', async () => {
    const wrapper = mount(KnowledgeAdminView, {
      global: { plugins: [createPinia(), ElementPlus] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('教材')
    expect(wrapper.text()).toContain('构建任务')
    expect(wrapper.text()).toContain('版本审核')
    expect(wrapper.text()).toContain('纠错队列')
    expect(wrapper.text()).toContain('示例出版社')
    expect(wrapper.text()).toContain('需要处理')
    expect(api.listTextbooks).toHaveBeenCalledOnce()
    expect(api.listBuilds).toHaveBeenCalledOnce()
    expect(api.listCorrections).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('rejects a non-PDF before upload', async () => {
    const wrapper = mount(KnowledgeAdminView, {
      global: { plugins: [createPinia(), ElementPlus] },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as {
      validateUploadFile: (file: File) => boolean
    }
    expect(vm.validateUploadFile(new File(['x'], 'notes.txt', { type: 'text/plain' }))).toBe(false)
    wrapper.unmount()
  })
})
