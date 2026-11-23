import client from './client'

export interface Student {
  id: number
  name: string
  grade: string
  subject: string
  level: string
  prefer_style?: string
}

export interface MemoryItem {
  id: number
  memory_type: string
  content: string
  confidence: number
  strength: number
  mastery: string
  knowledge_point_id?: number | null
  created_at?: string
  last_accessed_at?: string | null
  last_reviewed_at?: string | null
  status?: string
}

export interface MemoryPage {
  total: number
  page: number
  page_size: number
  items: MemoryItem[]
}

export interface ChatResponse {
  session_id: number
  response: string
  assistant_message_id: number
  evidence_ledger_id: number
  evidence: AnswerEvidence
}

export interface KnowledgeEvidence {
  knowledge_point_id: number
  title: string
  version_id?: number
  version_no?: number
  page_range?: [number | null, number | null] | null
  similarity?: number
  adopted?: boolean
  legacy?: boolean
  textbook?: { filename?: string; publisher?: string; edition?: string; volume?: string } | string
}

export interface AnswerEvidence {
  knowledge: KnowledgeEvidence[]
  memory?: unknown[]
  gap: { evidence_gap?: boolean; messages?: string[]; reasons?: string[] }
}

export interface ReviewPlan {
  id: number
  target_type: string
  target_id: number
  interval_days: number
  next_review_at: string
  content?: string
  strength?: number
}

export interface GraphNode {
  id: number
  title: string
  chapter: string
  difficulty: string
}

export interface GraphEdge {
  source: number
  target: number
  type: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface LearningPathStep {
  id: number
  title: string
  difficulty: string
  subject: string
  grade?: string
  is_target: boolean
  mastery: string
  wrong_count: number
  review_due: boolean
  next_review_at?: string | null
  reasons: string[]
}

export interface LearningPathResponse {
  target: { id: number; title: string; subject: string }
  path: LearningPathStep[]
  evidence_gap?: string | null
}

export interface StudentProfile {
  id: number
  name: string
  grade: string
  level: string
  weaknesses: string[]
  strengths: string[]
}

export interface WrongQuestion {
  id: number
  question_text: string
  answer?: string
  analysis?: string
  error_type?: string
  mastered: number
  created_at?: string
}

export interface StudentReport {
  student: { id: number; name: string; grade: string; subject: string }
  memory_counts: Record<string, number>
  memory_total: number
  review: { total: number; due: number; done: number; pending: number }
  wrong_questions: { total: number; mastered: number; unmastered: number }
  weaknesses: string[]
  strengths: string[]
  timeline: ReportTimelinePoint[]
}

export interface ReportTimelinePoint {
  date: string
  mastery_changes: number
  wrong_added: number
  wrong_mastered: number
  review_succeeded: number
  review_failed: number
  review_completion_rate: number | null
  event_ids: number[]
}

export interface SessionMessage {
  id: number
  role: string
  content: string
  created_at?: string | null
}

export interface CorrectionCreate {
  assistant_message_id: number
  category: 'knowledge' | 'question' | 'explanation' | 'memory'
  target_id?: number
  proposed_value?: Record<string, unknown>
  reason: string
}

export interface QuizGenerateRequest {
  student_id: number
  subject: string
  count: number
  difficulty: string
}

export interface QuizQuestion {
  type: string
  question: string
  options?: string[]
  answer: string
  analysis: string
  knowledge_point_id?: number | null
  knowledge_point_title?: string
}

export interface WrongQuestionCreate {
  student_id: number
  question_text: string
  answer?: string
  analysis?: string
  error_type?: string
  knowledge_point_id?: number | null
}

export interface LearningGoalResponse {
  id: number
  student_id: number
  current_version: { id: number; version_no: number; knowledge_version_id: number; target_date: string; weekly_minutes: number; subject: string; target_level: string; status: string; change_reason: string; target_knowledge_point_ids: number[] }
}
export interface DiagnosticSessionResponse {
  id: number
  status: string
  goal_version_id: number
  knowledge_version_id: number
  missing_question_knowledge_point_ids: number[]
  questions: Array<{ question_id: number; stem: string; question_type: string; options?: string[]; raw_answer?: Record<string, unknown> | null; suggested_score?: number | null; suggestion_basis?: Record<string, unknown> | null; final_score?: number | null; final_score_reason?: string | null; confirmed: boolean }>
}
export interface LearningPlanResponse {
  id: number
  status: string
  scheduled_minutes: number
  missing_minutes: number
  goal_version_id: number
  diagnostic_session_id?: number | null
  adjustment_reason: string
  items: Array<{ knowledge_point_id: number; week_no?: number | null; estimated_minutes: number; reasons: string[]; completion_condition: string; evidence: Record<string, unknown> | null; scheduled: boolean }>
}

export const eduApi = {
  // 学生
  listStudents: () => client.get<Student[]>('/students').then((r) => r.data),
  createStudent: (data: Partial<Student>) =>
    client.post<Student>('/students', data).then((r) => r.data),
  getProfile: (sid: number) =>
    client.get<StudentProfile>(`/students/${sid}/profile`).then((r) => r.data),
  getMemories: (sid: number, params?: { memory_type?: string; page?: number; page_size?: number }) =>
    client.get<MemoryPage>(`/students/${sid}/memories`, { params }).then((r) => r.data),
  getReviewPlans: (sid: number) =>
    client.get<ReviewPlan[]>(`/students/${sid}/review-plans`).then((r) => r.data),
  getWrongQuestions: (sid: number) =>
    client.get<WrongQuestion[]>(`/students/${sid}/wrong-questions`).then((r) => r.data),
  getReport: (sid: number) =>
    client.get<StudentReport>(`/students/${sid}/report`).then((r) => r.data),

  // 对话
  chat: (student_id: number, message: string, session_id?: number) =>
    client
      .post<ChatResponse>('/chat', { student_id, message, session_id })
      .then((r) => r.data),
  getSessionMessages: (sessionId: number) =>
    client
      .get<{ session_id: number; student_id: number; messages: SessionMessage[] }>(
        `/sessions/${sessionId}/messages`,
      )
      .then((r) => r.data),
  endSession: (sessionId: number) =>
    client.post(`/sessions/${sessionId}/end`).then((r) => r.data),
  getAnswerEvidence: (assistantMessageId: number) =>
    client.get<{ id: number; knowledge_evidence: KnowledgeEvidence[]; memory_evidence: unknown[]; evidence_gap: AnswerEvidence['gap'] }>(`/knowledge/evidence/${assistantMessageId}`).then((r) => r.data),
  submitCorrection: (data: CorrectionCreate) =>
    client.post('/corrections', data).then((r) => r.data),

  // 复习
  reviewMemory: (memory_id: number, success: boolean) =>
    client.post(`/memories/${memory_id}/review`, { success }).then((r) => r.data),
  confirmReviewPlan: (memory_id: number) =>
    client.post(`/memories/${memory_id}/review-plan`).then((r) => r.data),

  // 练习与错题
  generateQuiz: (data: QuizGenerateRequest) =>
    client
      .post<{ count: number; questions: QuizQuestion[] }>('/quiz/generate', data)
      .then((r) => r.data),
  recordWrongQuestion: (data: WrongQuestionCreate) =>
    client.post('/wrong-questions', data).then((r) => r.data),

  // 知识图谱
  getGraph: (subject?: string) =>
    client.get<GraphData>('/knowledge/graph', { params: { subject } }).then((r) => r.data),
  getKnowledgeStats: (subject?: string) =>
    client.get('/knowledge/stats', { params: { subject } }).then((r) => r.data),
  getKnowledgeDetail: (id: number) =>
    client.get(`/knowledge/${id}`).then((r) => r.data),
  getLearningPath: (id: number, studentId: number) =>
    client
      .get<LearningPathResponse>(`/knowledge/path/${id}`, {
        params: { student_id: studentId },
      })
      .then((r) => r.data),
  getSubjects: () =>
    client.get<{ subjects: string[] }>('/knowledge/subjects').then((r) => r.data.subjects),

  // v1.8 学习目标、诊断与计划
  getLearningGoal: (studentId: number) => client.get<LearningGoalResponse>(`/learning/goals/${studentId}`).then((r) => r.data),
  createLearningGoal: (data: { student_id: number; target_date: string; weekly_minutes: number; subject: string; target_level: string; target_knowledge_point_ids: number[] }) => client.post<LearningGoalResponse>('/learning/goals', data).then((r) => r.data),
  updateLearningGoal: (goalId: number, data: { target_date?: string; weekly_minutes?: number; target_knowledge_point_ids?: number[]; status?: 'active' | 'paused' | 'ended'; change_reason: string }) => client.patch<LearningGoalResponse>(`/learning/goals/${goalId}`, data).then((r) => r.data),
  startDiagnostic: (data: { student_id: number; goal_id: number }) => client.post<DiagnosticSessionResponse>('/learning/diagnostics', data).then((r) => r.data),
  getLatestDiagnostic: (goalId: number) => client.get<DiagnosticSessionResponse>(`/learning/diagnostics/goals/${goalId}`).then((r) => r.data),
  saveDiagnosticAnswer: (sessionId: number, questionId: number, data: { raw_answer: Record<string, unknown>; elapsed_seconds?: number; confidence?: number }) => client.put<{ final_score: number | null; confirmed: boolean }>(`/learning/diagnostics/${sessionId}/answers/${questionId}`, data).then((r) => r.data),
  confirmDiagnosticScore: (sessionId: number, questionId: number, final_score: number, final_score_reason?: string) => client.post<{ final_score: number; final_score_reason?: string | null; confirmed: boolean }>(`/learning/diagnostics/${sessionId}/answers/${questionId}/confirm`, { final_score, final_score_reason }).then((r) => r.data),
  retryDiagnosticSuggestion: (sessionId: number, questionId: number) => client.post<{ suggested_score: number | null; suggestion_basis: Record<string, unknown> | null }>(`/learning/diagnostics/${sessionId}/answers/${questionId}/retry-suggestion`).then((r) => r.data),
  submitDiagnostic: (sessionId: number) => client.post<{ status: string; results: Array<{ knowledge_point_id: number; mastery?: string; evidence_status: string; score_rate?: number }> }>(`/learning/diagnostics/${sessionId}/submit`).then((r) => r.data),
  getDiagnosticReport: (sessionId: number) => client.get<{ status: string; results: Array<{ knowledge_point_id: number; knowledge_point_title?: string | null; source_page_range?: [number, number] | null; mastery?: string; evidence_status: string; score_rate?: number; valid_answer_count: number; evidence: Record<string, unknown> | null }> }>(`/learning/diagnostics/${sessionId}/report`).then((r) => r.data),
  createLearningPlan: (data: { student_id: number; goal_id: number; adjustment_reason?: string }) => client.post<LearningPlanResponse>('/learning/plans', data).then((r) => r.data),
  getLearningPlanHistory: (goalId: number) => client.get<{ plans: LearningPlanResponse[] }>(`/learning/plans/${goalId}`).then((r) => r.data),

  // 参数后台（v1.1）
  getSettings: () => client.get('/settings').then((r) => r.data),
  updateSettings: (data: Record<string, number>) =>
    client.put('/settings', data).then((r) => r.data),

  // 记忆管理（v1.1）
  updateMemory: (id: number, data: { content?: string; mastery?: string; status?: string }) =>
    client.put(`/memories/${id}`, data).then((r) => r.data),
  deleteMemory: (id: number) => client.delete(`/memories/${id}`).then((r) => r.data),
}
