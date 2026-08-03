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
              <div class="bubble" v-html="m.html"></div>
            </div>
            <div v-if="loading" class="msg assistant">
              <div class="bubble loading">正在思考…（记忆提取中）</div>
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
          <div class="side-title">🧠 学生记忆（实时）</div>
          <el-empty v-if="!memories.length" description="暂无记忆，聊几句就有了" :image-size="60" />
          <div v-for="mem in memories" :key="mem.id" class="mem-card">
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
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import { useStudentStore } from '../stores/student'
import { eduApi, type MemoryItem } from '../api/edu'

const md = new MarkdownIt({ html: false, linkify: true })

const store = useStudentStore()
const studentId = ref<number | null>(null)
const input = ref('')
const messages = ref<{ role: string; text: string; html: string }[]>([])
const memories = ref<MemoryItem[]>([])
const loading = ref(false)
const msgListRef = ref<HTMLElement | null>(null)

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

async function refreshMemories() {
  if (!studentId.value) return
  memories.value = await eduApi.getMemories(studentId.value)
}

function onStudentChange() {
  store.sessionId = null
  messages.value = []
  refreshMemories()
}

function newSession() {
  store.sessionId = null
  messages.value = []
  ElMessage.success('已开启新会话')
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
  try {
    const resp = await eduApi.chat(studentId.value, text, store.sessionId ?? undefined)
    store.sessionId = resp.session_id
    messages.value.push({ role: 'assistant', text: resp.response, html: mdToHtml(resp.response) })
    await refreshMemories()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '对话失败')
  } finally {
    loading.value = false
    scrollBottom()
  }
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
    await refreshMemories()
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
.bubble { max-width: 88%; padding: 10px 14px; border-radius: 10px; line-height: 1.7; font-size: 14px; word-break: break-word; }
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
.mem-card { background: #fff; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; border: 1px solid #ebeef5; }
.mem-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.mem-conf { font-size: 12px; color: #909399; }
.mem-content { font-size: 13px; color: #303133; }
</style>