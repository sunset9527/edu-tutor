import client from './client'

export interface Textbook {
  id: number
  school_stage?: string
  grade: string
  subject: string
  publisher: string
  edition: string
  volume: string
  original_filename?: string
  file_sha256: string
  page_count?: number | null
  source_note?: string
  license_note?: string
  active_version_id?: number | null
}

export interface BuildTask {
  id: number
  textbook_id: number
  target_version_id?: number | null
  status: string
  stage: string
  total_units: number
  completed_units: number
  failed_units: number
  lease_owner?: string | null
  lease_expires_at?: string | null
  error_summary?: string | null
  units?: Array<{ id: number; unit_type: string; sequence: number; status: string; error_detail?: string | null }>
  events?: Array<{ id: number; level: string; stage: string; message: string; created_at?: string | null }>
}

export interface KnowledgeVersion {
  id: number
  textbook_id: number
  version_no: number
  parent_version_id?: number | null
  status: string
  point_count: number
  edge_count: number
  source_chunk_count: number
  vector_count: number
  points: Array<{ id: number; title: string; chapter?: string | null; difficulty: string; provenance_gap: boolean }>
  source_chunks: Array<{ id: number; sequence: number; start_page?: number | null; end_page?: number | null; parse_method: string }>
  reviews: Array<{ id: number; conclusion: string; note?: string | null }>
}

export interface CorrectionTicket {
  id: number
  category: string
  target_type?: string
  target_id?: number
  original_value: Record<string, unknown>
  proposed_value?: Record<string, unknown> | null
  reason: string
  status: string
  handling_note?: string | null
  created_at?: string | null
}

type Page<T> = { items: T[]; total: number }

export const governanceApi = {
  listTextbooks: () => client.get<Page<Textbook>>('/admin/textbooks').then((r) => r.data),
  uploadTextbook: (form: FormData) =>
    client.post<Textbook>('/admin/textbooks', form).then((r) => r.data),
  createBuild: (textbookId: number, data: { group_size: number; use_ocr: boolean }) =>
    client
      .post<BuildTask>(`/admin/textbooks/${textbookId}/builds`, data, {
        headers: { 'Idempotency-Key': crypto.randomUUID() },
      })
      .then((r) => r.data),
  listBuilds: () => client.get<Page<BuildTask>>('/admin/builds').then((r) => r.data),
  getBuild: (taskId: number) => client.get<BuildTask>(`/admin/builds/${taskId}`).then((r) => r.data),
  resumeBuild: (taskId: number) => client.post<BuildTask>(`/admin/builds/${taskId}/resume`).then((r) => r.data),
  retryFailures: (taskId: number) =>
    client.post<BuildTask>(`/admin/builds/${taskId}/retry-failures`).then((r) => r.data),
  cancelBuild: (taskId: number) => client.post<BuildTask>(`/admin/builds/${taskId}/cancel`).then((r) => r.data),
  getVersion: (versionId: number) =>
    client.get<KnowledgeVersion>(`/admin/versions/${versionId}`).then((r) => r.data),
  reviewVersion: (versionId: number, data: Record<string, unknown>) =>
    client.post(`/admin/versions/${versionId}/reviews`, data).then((r) => r.data),
  activateVersion: (versionId: number, expectedActiveVersionId: number | null) =>
    client.post<KnowledgeVersion>(`/admin/versions/${versionId}/activate`, {
      expected_active_version_id: expectedActiveVersionId,
    }).then((r) => r.data),
  rollbackTextbook: (textbookId: number, targetVersionId: number, expectedActiveVersionId: number | null) =>
    client.post<KnowledgeVersion>(`/admin/textbooks/${textbookId}/rollback`, {
      target_version_id: targetVersionId,
      expected_active_version_id: expectedActiveVersionId,
    }).then((r) => r.data),
  listCorrections: (params?: { status?: string; category?: string }) =>
    client.get<Page<CorrectionTicket>>('/admin/corrections', { params }).then((r) => r.data),
  acceptCorrection: (ticketId: number, note: string) =>
    client.post<CorrectionTicket>(`/admin/corrections/${ticketId}/accept`, { note }).then((r) => r.data),
  rejectCorrection: (ticketId: number, note: string) =>
    client.post<CorrectionTicket>(`/admin/corrections/${ticketId}/reject`, { note }).then((r) => r.data),
}
