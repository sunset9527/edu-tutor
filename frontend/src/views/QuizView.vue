<template>
  <div class="quiz-page">
    <el-card shadow="never" class="quiz-card">
      <template #header>
        <div class="row-between">
          <span>🧠 智能出题（基于薄弱点 + 知识图谱）</span>
          <el-button type="primary" :loading="loading" @click="generate">生成题目</el-button>
        </div>
      </template>

      <div class="quiz-options">
        <el-select v-model="studentId" placeholder="选择学生" style="width: 160px" @change="loadReport">
          <el-option v-for="s in studentStore.students" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-select v-model="subject" style="width: 110px">
          <el-option v-for="s in subjects" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="difficulty" style="width: 100px">
          <el-option label="基础" value="基础" />
          <el-option label="中等" value="中等" />
          <el-option label="拔高" value="拔高" />
        </el-select>
        <el-input-number v-model="count" :min="1" :max="10" />
        <span class="tip">道</span>
      </div>

      <el-empty v-if="!questions.length && !loading" description="点「生成题目」，基于薄弱知识点出针对性练习" />
      <el-empty v-else-if="!questions.length && loading" description="AI 出题中，请稍候…" />

      <div v-for="(q, i) in questions" :key="i" class="quiz-item">
        <div class="quiz-q">
          <el-tag size="small" :type="q.type === '选择' ? 'primary' : q.type === '填空' ? 'warning' : 'success'" effect="plain">
            {{ q.type }}
          </el-tag>
          <span class="q-text">{{ i + 1 }}. {{ q.question }}</span>
        </div>
        <div v-if="q.options && q.options.length" class="quiz-options-list">
          <div v-for="opt in q.options" :key="opt" class="opt">{{ opt }}</div>
        </div>
        <div class="quiz-kp">📌 知识点：{{ q.knowledge_point_title }}</div>
        <div class="quiz-actions">
          <el-button size="small" type="danger" plain @click="wrong(q)">我错了 → 入错题本</el-button>
          <el-button size="small" type="success" plain @click="showAnswer(q)">看答案</el-button>
        </div>
        <el-collapse-transition>
          <div v-if="q.show" class="quiz-answer">
            <div>✅ 答案：{{ q.answer }}</div>
            <div>💡 解析：{{ q.analysis }}</div>
          </div>
        </el-collapse-transition>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { eduApi } from '../api/edu'
import { useStudentStore } from '../stores/student'

const studentStore = useStudentStore()
const subjects = ['数学', '语文', '英语', '生物']
const studentId = ref<number | null>(null)
const subject = ref('数学')
const difficulty = ref('中等')
const count = ref(3)
const questions = ref<any[]>([])
const loading = ref(false)

async function generate() {
  if (!studentId.value) {
    ElMessage.warning('请先选择学生')
    return
  }
  loading.value = true
  questions.value = []
  try {
    const r = await eduApi.generateQuiz({
      student_id: studentId.value,
      subject: subject.value,
      count: count.value,
      difficulty: difficulty.value,
    })
    questions.value = r.questions.map((q: any) => ({ ...q, show: false }))
    if (!r.questions.length) ElMessage.warning('出题失败，请重试')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '出题失败')
  } finally {
    loading.value = false
  }
}

function showAnswer(q: any) {
  q.show = !q.show
}

async function wrong(q: any) {
  await eduApi.recordWrongQuestion({
    student_id: studentId.value,
    question_text: q.question,
    answer: '（待订正）',
    analysis: q.analysis,
    error_type: '概念不清',
    knowledge_point_id: q.knowledge_point_id,
  })
  ElMessage.success('已加入错题本，可在学习报告查看')
}

onMounted(async () => {
  await studentStore.loadStudents()
  if (studentStore.students.length) studentId.value = studentStore.students[0].id
})
</script>

<style scoped>
.quiz-options { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.tip { color: #909399; font-size: 13px; }
.quiz-item { border: 1px solid #eef0f3; border-radius: 8px; padding: 12px; margin-bottom: 10px; background: #fff; }
.quiz-q { display: flex; gap: 8px; align-items: flex-start; }
.q-text { font-size: 14px; line-height: 1.6; }
.quiz-options-list { margin: 8px 0 4px 30px; }
.opt { font-size: 13px; color: #606266; padding: 2px 0; }
.quiz-kp { font-size: 12px; color: #909399; margin-top: 6px; }
.quiz-actions { margin-top: 8px; }
.quiz-answer { background: #f8fafc; border-radius: 6px; padding: 10px; margin-top: 8px; font-size: 13px; line-height: 1.7; }
</style>
