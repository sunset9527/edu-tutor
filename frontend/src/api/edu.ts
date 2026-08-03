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
}

export interface ChatResponse {
  session_id: number
  response: string
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

export const eduApi = {
  // 学生
  listStudents: (user_id?: number) => client.get<Student[]>('/students', { params: { user_id } }).then((r) => r.data),
  createStudent: (data: Partial<Student>) =>
    client.post<Student>('/students', data).then((r) => r.data),
  getProfile: (sid: number) =>
    client.get<StudentProfile>(`/students/${sid}/profile`).then((r) => r.data),
  getMemories: (sid: number) =>
    client.get<MemoryItem[]>(`/students/${sid}/memories`).then((r) => r.data),
  getReviewPlans: (sid: number) =>
    client.get<ReviewPlan[]>(`/students/${sid}/review-plans`).then((r) => r.data),
  getWrongQuestions: (sid: number) =>
    client.get<WrongQuestion[]>(`/students/${sid}/wrong-questions`).then((r) => r.data),

  // 对话
  chat: (student_id: number, message: string, session_id?: number) =>
    client
      .post<ChatResponse>('/chat', { student_id, message, session_id })
      .then((r) => r.data),

  // 复习
  reviewMemory: (memory_id: number, success: boolean) =>
    client.post(`/memories/${memory_id}/review`, { success }).then((r) => r.data),

  // 知识图谱
  getGraph: (subject?: string) =>
    client.get<GraphData>('/knowledge/graph', { params: { subject } }).then((r) => r.data),
  getKnowledgeStats: (subject?: string) =>
    client.get('/knowledge/stats', { params: { subject } }).then((r) => r.data),
  getKnowledgeDetail: (id: number) =>
    client.get(`/knowledge/${id}`).then((r) => r.data),
  getLearningPath: (id: number) => client.get(`/knowledge/path/${id}`).then((r) => r.data),

  // 参数后台（v1.1）
  getSettings: () => client.get('/settings').then((r) => r.data),
  updateSettings: (data: Record<string, number>) =>
    client.put('/settings', data).then((r) => r.data),

  // 记忆管理（v1.1）
  updateMemory: (id: number, data: { content?: string; mastery?: string; status?: string }) =>
    client.put(`/memories/${id}`, data).then((r) => r.data),
  deleteMemory: (id: number) => client.delete(`/memories/${id}`).then((r) => r.data),
}
