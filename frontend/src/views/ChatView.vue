<template>
  <div class="chat-page">
    <el-card shadow="never" class="chat-card">
      <template #header>
        <div class="chat-header">
          <el-select v-model="studentId" placeholder="选择学生" style="width: 220px" @change="onStudentChange">
            <el-option v-for="s in store.students" :key="s.id" :label="`${s.name}（${s.grade}·${s.subject}）`" :value="s.id" />
          </el-select>
          <el-tag v-if="store.current" type="info" effect="plain">{{ store.current.level }}</el-tag>
          <el-button type="primary" plain size="small" @click="newSession" style="margin-left: 8px">新会话</el-button>
        </div>
      </template>

      <div class="chat-body">
        <div class="chat-main">
          <div ref="msgListRef" class="msg-list">
            <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
              <div class="answer-wrap">
                <div class="bubble" v-html="m.html"></div>
                <div v-if="m.role === 'assistant' && m.evidence" class="answer-evidence">
                  <div class="evidence-heading"><span>教材证据</span><small v-if="m.assistantMessageId">消息 #{{ m.assistantMessageId }}</small></div>
                  <div v-if="m.evidence.gap?.evidence_gap" class="gap-message">{{ gapText(m.evidence.gap) }}</div>
                  <div v-for="item in adoptedKnowledge(m.evidence.knowledge)" :key="item.knowledge_point_id" class="inline-source">
                    <strong>{{ item.title }}</strong><span>{{ sourceMeta(item) }}</span>
                  </div>
                  <el-button v-if="m.assistantMessageId" size="small" plain type="primary" @click="openFeedback(m)">反馈此回答</el-button>
                </div>
              </div>
            </div>
            <div v-if="loading && !streamingAnswer" class="msg assistant">
              <div class="bubble loading">{{ stageText }}</div>
            </div>
          </div>
          <div class="chat-input">
            <el-input
              v-model="input"
              type="textarea"
              :rows="2"
              placeholder="输入问题，例如：一元一次方程怎么解？"
              @keydown.enter.exact.prevent="send"
            />
            <el-button type="primary" :loading="loading" @click="send">发送</el-button>
          </div>
        </div>

        <div class="chat-side">
          <div class="side-title">本轮教材证据</div>
          <el-empty v-if="!currentEvidence.knowledge.length && !currentEvidence.gap?.evidence_gap" description="发送问题后显示教材来源与缺口。" :image-size="52" />
          <el-alert v-if="currentEvidence.gap?.evidence_gap" :title="gapText(currentEvidence.gap)" type="warning" :closable="false" show-icon class="gap-alert" />
          <div v-for="item in currentEvidence.knowledge" :key="item.knowledge_point_id" class="evidence-card" :class="{ muted: !item.adopted }">
            <div class="mem-head"><el-tag size="small" :type="item.adopted ? 'success' : 'info'">{{ item.adopted ? '已采用' : '仅候选' }}</el-tag><span class="mem-conf">{{ similarityText(item.similarity) }}</span></div>
            <div class="evidence-title">{{ item.title }}</div>
            <div class="evidence-meta">{{ sourceMeta(item) }}</div>
            <el-tag v-if="item.legacy" size="small" type="warning" effect="plain">legacy 来源缺口</el-tag>
          </div>
          <div class="side-title">🧠 本轮记忆轨迹</div>
          <el-empty v-if="!memoryTrace.length" description="发送问题后显示真实检索与写入结果" :image-size="60" />
          <div v-for="mem in memoryTrace" :key="`${mem.kind}-${mem.id}`" class="mem-card">
            <div class="mem-head">
              <el-tag size="small" :type="traceColor(mem.kind)">{{ traceLabel(mem.kind) }}</el-tag>
              <span class="mem-conf" v-if="mem.memory_type">{{ typeLabel(mem.memory_type) }}</span>
            </div>
            <div class="mem-content">{{ mem.content }}</div>
          </div>
          <div v-if="suggestions.length" class="side-title library-title">待确认任务</div>
          <div v-for="(item, index) in suggestions" :key="`${item.type}-${index}`" class="suggest-card">
            <div>{{ item.type === 'wrong_question' ? '加入错题本' : '加入复习计划' }}</div>
            <div class="mem-content">{{ item.question_text || item.content }}</div>
            <el-button size="small" type="primary" plain @click="confirmSuggestion(item, index)">确认</el-button>
          </div>
          <div class="side-title library-title">记忆库（{{ memoryTotal }}）</div>
          <div v-for="mem in memories.slice(0, 8)" :key="mem.id" class="mem-card subdued">
            <div class="mem-head">
              <el-tag size="small" :type="typeColor(mem.memory_type)">{{ typeLabel(mem.memory_type) }}</el-tag>
              <span class="mem-conf">{{ (mem.confidence * 100).toFixed(0) }}%</span>
            </div>
            <div class="mem-content">{{ mem.content }}</div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
  <el-dialog v-model="feedbackVisible" title="反馈此回答" width="min(520px, calc(100% - 32px))" :close-on-click-modal="!submitting">
    <el-form label-position="top">
      <el-form-item label="反馈类型" required><el-select v-model="feedback.category"><el-option label="教材知识" value="knowledge" /><el-option label="回答讲解" value="explanation" /><el-option label="题目" value="question" /><el-option label="学生记忆" value="memory" /></el-select></el-form-item>
      <el-form-item label="建议修改"><el-input v-model="feedback.proposed" type="textarea" :rows="3" placeholder="可选：说明正确内容或建议表达" /></el-form-item>
      <el-form-item label="反馈原因" required><el-input v-model="feedback.reason" type="textarea" :rows="3" placeholder="请说明哪里不准确或不完整" /></el-form-item>
      <p v-if="feedbackError" class="feedback-error" role="alert">{{ feedbackError }}</p>
    </el-form>
    <template #footer><el-button :disabled="submitting" @click="feedbackVisible = false">取消</el-button><el-button type="primary" :loading="submitting" :disabled="!feedback.reason.trim()" @click="submitFeedback">提交反馈</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { useStudentStore } from '../stores/student'
import { eduApi, type AnswerEvidence, type KnowledgeEvidence, type MemoryItem } from '../api/edu'
import { streamChat, type SSEEvent } from '../api/sse'
import { clearStoredSession, loadStoredSession, storeSession } from '../utils/session'

const md = new MarkdownIt({ html: false, linkify: true })

const store = useStudentStore()
const studentId = ref<number | null>(null)
const input = ref('')
type ChatMessage = {
  role: string
  text: string
  html: string
  assistantMessageId?: number
  evidenceLedgerId?: number
  evidence?: AnswerEvidence
}
const messages = ref<ChatMessage[]>([])
const memories = ref<MemoryItem[]>([])
const memoryTotal = ref(0)
const loading = ref(false)
const stage = ref('idle')
const streamingAnswer = ref('')
type TraceKind = 'hit' | 'new' | 'updated'
const memoryTrace = ref<(Partial<MemoryItem> & { id: number; content: string; kind: TraceKind })[]>([])
const suggestions = ref<any[]>([])
const msgListRef = ref<HTMLElement | null>(null)
const currentEvidence = ref<AnswerEvidence>({ knowledge: [], memory: [], gap: {} })
const feedbackVisible = ref(false)
const submitting = ref(false)
const feedbackError = ref('')
const feedbackMessage = ref<ChatMessage | null>(null)
const feedback = ref({ category: 'explanation' as 'knowledge' | 'question' | 'explanation' | 'memory', proposed: '', reason: '' })

const stageText = computed(() => ({
  starting: '正在启动回答…',
  retrieving: '正在检索与当前问题相关的记忆…',
  generating: '正在生成回答…',
  saving: '正在保存本轮消息…',
  extracting: '正在分析本轮产生的新记忆…',
  profile: '正在刷新学生画像…',
}[stage.value] || '正在处理…'))

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')
}
function mdToHtml(s: string) {
  return md.render(s || '')
}
function typeLabel(t: string) {
  return t === 'semantic' ? '画像' : t === 'episodic' ? '情景' : '策略'
}
function typeColor(t: string) {
  return t === 'semantic' ? 'success' : t === 'episodic' ? 'primary' : 'warning'
}
function adoptedKnowledge(items: KnowledgeEvidence[]) { return items.filter((item) => item.adopted) }
function similarityText(value?: number) { return typeof value === 'number' ? `相似度 ${(value * 100).toFixed(0)}%` : '相似度未知' }
function sourceMeta(item: KnowledgeEvidence) {
  const textbook = typeof item.textbook === 'string' ? item.textbook : item.textbook?.filename || item.textbook?.publisher || '教材未命名'
  const pages = item.page_range?.[0] ? `第 ${item.page_range[0]}-${item.page_range[1] || item.page_range[0]} 页` : '页码未知'
  return `${textbook} · v${item.version_no ?? item.version_id ?? '—'} · ${pages}`
}
function gapText(gap: AnswerEvidence['gap']) { return gap.messages?.join('；') || '当前教材证据不足，以下回答不应被视为教材原文结论。' }

async function refreshMemories() {
  if (!studentId.value) return
  const page = await eduApi.getMemories(studentId.value, { page: 1, page_size: 100 })
  memories.value = page.items
  memoryTotal.value = page.total
}

async function restoreSession() {
  if (!studentId.value) return
  const stored = loadStoredSession(studentId.value)
  store.sessionId = stored
  messages.value = []
  if (!stored) return
  try {
    const data = await eduApi.getSessionMessages(stored)
    if (data.student_id !== studentId.value) throw new Error('会话学生不匹配')
    const restored: ChatMessage[] = data.messages
      .filter((row) => row.role === 'user' || row.role === 'assistant')
      .map((row) => ({
        role: row.role,
        text: row.content,
        html: row.role === 'assistant' ? mdToHtml(row.content) : escapeHtml(row.content),
        assistantMessageId: row.role === 'assistant' ? row.id : undefined,
      }))
    messages.value = restored
    const assistantRows = restored.filter((row) => row.assistantMessageId)
    const evidenceRows = await Promise.all(assistantRows.map(async (row) => {
      try {
        const evidence = await eduApi.getAnswerEvidence(row.assistantMessageId!)
        row.evidenceLedgerId = evidence.id
        row.evidence = { knowledge: evidence.knowledge_evidence, memory: evidence.memory_evidence, gap: evidence.evidence_gap }
      } catch { /* 旧会话没有证据账本时保持原对话可读 */ }
    }))
    void evidenceRows
    scrollBottom()
  } catch {
    clearStoredSession(studentId.value)
    store.sessionId = null
  }
}

async function onStudentChange() {
  memoryTrace.value = []
  suggestions.value = []
  currentEvidence.value = { knowledge: [], memory: [], gap: {} }
  await Promise.all([refreshMemories(), restoreSession()])
}

async function newSession() {
  if (store.sessionId) {
    try {
      await eduApi.endSession(store.sessionId)
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || '结束当前会话失败')
      return
    }
  }
  if (studentId.value) clearStoredSession(studentId.value)
  store.sessionId = null
  messages.value = []
  memoryTrace.value = []
  suggestions.value = []
  currentEvidence.value = { knowledge: [], memory: [], gap: {} }
  await refreshMemories()
  ElMessage.success('已开启新会话')
}

function handleStreamEvent(event: SSEEvent) {
  const data = event.data as any
  if (event.event === 'generation_started') stage.value = 'retrieving'
  if (event.event === 'memory_retrieved') {
    memoryTrace.value = (data.selected || []).map((item: any) => ({
      id: item.memory_id,
      content: item.content,
      memory_type: item.memory_type,
      kind: 'hit' as const,
    }))
    stage.value = 'generating'
  }
  if (event.event === 'knowledge_retrieved') {
    currentEvidence.value = {
      knowledge: data.candidates || [],
      memory: [],
      gap: data.evidence_gap || {},
    }
  }
  if (event.event === 'response_chunk') {
    streamingAnswer.value += data.text || ''
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant') {
      last.text = streamingAnswer.value
      last.html = mdToHtml(streamingAnswer.value)
    } else {
      messages.value.push({
        role: 'assistant',
        text: streamingAnswer.value,
        html: mdToHtml(streamingAnswer.value),
      })
    }
    scrollBottom()
  }
  if (event.event === 'messages_saved') stage.value = 'extracting'
  if (event.event === 'evidence_recorded') {
    const last = [...messages.value].reverse().find((row) => row.role === 'assistant')
    if (last) {
      last.assistantMessageId = data.assistant_message_id
      last.evidenceLedgerId = data.evidence_ledger_id
      last.evidence = { ...currentEvidence.value, gap: data.evidence_gap || currentEvidence.value.gap }
    }
  }
  if (event.event === 'memory_extracted') {
    const additions = (data.new_memories || []).map((item: any) => ({ ...item, kind: 'new' as const }))
    const updates = (data.updated_memories || []).map((item: any) => ({ ...item, kind: 'updated' as const }))
    memoryTrace.value.push(...additions, ...updates)
    suggestions.value = data.suggestions || []
    stage.value = 'profile'
  }
  if (event.event === 'failed') throw new Error(data.error || '对话失败')
  if (event.event === 'completed' && data.evidence) {
    const finalEvidence: AnswerEvidence = {
      ...data.evidence,
      knowledge: data.evidence.knowledge?.length ? data.evidence.knowledge : currentEvidence.value.knowledge,
      gap: data.evidence.gap || currentEvidence.value.gap,
    }
    currentEvidence.value = finalEvidence
    const last = [...messages.value].reverse().find((row) => row.role === 'assistant')
    if (last) last.evidence = finalEvidence
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || !studentId.value) {
    if (!studentId.value) ElMessage.warning('请先选择学生')
    return
  }
  input.value = ''
  messages.value.push({ role: 'user', text, html: escapeHtml(text) })
  scrollBottom()
  loading.value = true
  streamingAnswer.value = ''
  memoryTrace.value = []
  suggestions.value = []
  currentEvidence.value = { knowledge: [], memory: [], gap: {} }
  stage.value = 'starting'
  try {
    const sessionId = await streamChat(
      { student_id: studentId.value, message: text, session_id: store.sessionId ?? undefined },
      handleStreamEvent,
    )
    store.sessionId = sessionId
    storeSession(studentId.value, sessionId)
    await refreshMemories()
  } catch (e: any) {
    ElMessage.error(e?.message || e?.response?.data?.detail || '对话失败')
  } finally {
    loading.value = false
    stage.value = 'idle'
    scrollBottom()
  }
}

function openFeedback(message: ChatMessage) {
  if (!message.assistantMessageId) return
  feedbackMessage.value = message
  feedback.value = { category: 'explanation', proposed: '', reason: '' }
  feedbackError.value = ''
  feedbackVisible.value = true
}

async function submitFeedback() {
  const message = feedbackMessage.value
  if (!message?.assistantMessageId || !feedback.value.reason.trim()) return
  submitting.value = true
  feedbackError.value = ''
  try {
    await eduApi.submitCorrection({
      assistant_message_id: message.assistantMessageId,
      category: feedback.value.category,
      proposed_value: feedback.value.proposed.trim() ? { suggestion: feedback.value.proposed.trim() } : undefined,
      reason: feedback.value.reason.trim(),
    })
    feedbackVisible.value = false
    ElMessage.success('反馈已提交，管理员会按工单流程处理。')
  } catch (error: any) {
    feedbackError.value = error?.response?.data?.detail || '提交失败，请检查网络后重试。'
  } finally { submitting.value = false }
}

async function confirmSuggestion(item: any, index: number) {
  if (!studentId.value) return
  if (item.type === 'wrong_question') {
    await eduApi.recordWrongQuestion({
      student_id: studentId.value,
      question_text: item.question_text,
      answer: '（待订正）',
      knowledge_point_id: item.knowledge_point_id,
    })
    ElMessage.success('已加入错题本')
  } else {
    await eduApi.confirmReviewPlan(item.memory_id)
    ElMessage.success('已确认复习任务')
  }
  suggestions.value.splice(index, 1)
}

function traceLabel(kind: TraceKind) {
  return kind === 'hit' ? '本轮命中' : kind === 'new' ? '本轮新增' : '本轮更新'
}
function traceColor(kind: TraceKind) {
  return kind === 'hit' ? 'primary' : kind === 'new' ? 'success' : 'warning'
}

function scrollBottom() {
  nextTick(() => {
    if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight
  })
}

onMounted(async () => {
  await store.loadStudents()
  if (store.students.length) {
    studentId.value = store.students[0].id
    await Promise.all([refreshMemories(), restoreSession()])
  } else {
    ElMessage.warning('暂无学生，请到「学生管理」页创建')
  }
})
</script>

<style scoped>
.chat-page { height: 100%; }
.chat-card { height: 100%; display: flex; flex-direction: column; }
.chat-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; padding: 12px; min-height: 0; }
.chat-body { flex: 1; display: flex; gap: 12px; min-height: 0; }
.chat-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.msg-list { flex: 1; overflow-y: auto; padding: 8px; background: #fafafa; border-radius: 8px; }
.msg { margin-bottom: 12px; display: flex; }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.answer-wrap { max-width: 88%; }
.bubble { max-width: 88%; padding: 10px 14px; border-radius: 10px; line-height: 1.7; font-size: 14px; word-break: break-word; }
.answer-wrap .bubble { max-width: 100%; }
.msg.user .bubble { background: #409eff; color: #fff; border-top-right-radius: 2px; }
.msg.assistant .bubble { background: #fff; border: 1px solid #e4e7ed; border-top-left-radius: 2px; }
.bubble.loading { color: #909399; }

/* markdown 渲染样式（AI 回复） */
.bubble :deep(p) { margin: 4px 0; }
.bubble :deep(ul), .bubble :deep(ol) { padding-left: 22px; margin: 4px 0; }
.bubble :deep(li) { margin: 2px 0; }
.bubble :deep(h1), .bubble :deep(h2), .bubble :deep(h3) { font-size: 15px; font-weight: 700; margin: 10px 0 4px; }
.bubble :deep(strong) { font-weight: 700; }
.bubble :deep(code) { background: rgba(0,0,0,.06); padding: 1px 5px; border-radius: 3px; font-size: 12px; font-family: Consolas, monospace; }
.bubble :deep(pre) { background: #282c34; color: #abb2bf; padding: 10px 12px; border-radius: 6px; overflow-x: auto; margin: 6px 0; }
.bubble :deep(pre code) { background: none; color: inherit; padding: 0; }
.bubble :deep(blockquote) { border-left: 3px solid #d9d9d9; padding-left: 10px; color: #909399; margin: 6px 0; }
.bubble :deep(a) { color: #409eff; }
.bubble :deep(table) { border-collapse: collapse; margin: 6px 0; }
.bubble :deep(th), .bubble :deep(td) { border: 1px solid #d9d9d9; padding: 4px 8px; }

.chat-input { display: flex; gap: 8px; margin-top: 12px; align-items: flex-end; }
.chat-input .el-input { flex: 1; }
.chat-side { width: 300px; background: #fafafa; border-radius: 8px; padding: 12px; overflow-y: auto; }
.side-title { font-weight: 600; margin-bottom: 10px; font-size: 14px; }
.evidence-card, .answer-evidence { background: #f0f7ff; border: 1px solid #c6e2ff; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
.evidence-card.muted { background: #f8f9fb; border-color: #e4e7ed; opacity: .86; }
.evidence-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 4px; }
.evidence-meta, .inline-source span { color: #606266; display: block; font-size: 12px; line-height: 1.5; }
.gap-alert { margin-bottom: 8px; }
.answer-evidence { margin-top: 6px; max-width: 100%; }
.evidence-heading { align-items: center; color: #409eff; display: flex; font-size: 12px; font-weight: 600; justify-content: space-between; margin-bottom: 6px; }
.inline-source { border-top: 1px solid #d9ecff; padding: 6px 0; }
.inline-source:first-of-type { border-top: none; }
.inline-source strong { color: #303133; display: block; font-size: 13px; }
.gap-message, .feedback-error { color: #c45656; font-size: 12px; line-height: 1.5; margin: 6px 0; }
.library-title { margin-top: 16px; padding-top: 12px; border-top: 1px solid #e4e7ed; }
.mem-card { background: #fff; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; border: 1px solid #ebeef5; }
.mem-card.subdued { opacity: .82; }
.suggest-card { background: #fff7e6; border: 1px solid #ffe0a3; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
.suggest-card .el-button { margin-top: 6px; }
.mem-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.mem-conf { font-size: 12px; color: #909399; }
.mem-content { font-size: 13px; color: #303133; }
@media (max-width: 760px) {
  .chat-body { flex-direction: column; overflow-y: auto; }
  .chat-main { flex: none; min-height: 420px; }
  .chat-side { box-sizing: border-box; overflow: visible; width: 100%; }
  .answer-wrap { max-width: 94%; }
}
</style>
