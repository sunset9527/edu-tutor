<template>
  <div class="report-page">
    <el-row :gutter="12" style="margin-bottom: 12px" v-if="report">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-num">{{ report.memory_total }}</div>
          <div class="stat-label">记忆条数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-num">{{ report.review.done }}/{{ report.review.total }}</div>
          <div class="stat-label">复习完成</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-num">{{ report.wrong_questions.total }}</div>
          <div class="stat-label">错题总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-num">{{ report.review.due }}</div>
          <div class="stat-label">待复习</div>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" style="margin-bottom: 12px">
      <div class="row-between">
        <el-select v-model="studentId" placeholder="选择学生" style="width: 200px" @change="load">
          <el-option v-for="s in store.students" :key="s.id" :label="`${s.name}（${s.grade}）`" :value="s.id" />
        </el-select>
        <div v-if="profile" class="row-between" style="gap: 12px">
          <el-tag v-for="w in profile.weaknesses" :key="w" type="danger" effect="plain">薄弱: {{ w }}</el-tag>
        </div>
      </div>
    </el-card>

    <el-row :gutter="12">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>📅 待复习计划（遗忘曲线调度）</template>
          <el-empty v-if="!plans.length" description="暂无到期待复习任务" :image-size="60" />
          <div v-for="p in plans" :key="p.id" class="plan-row">
            <div class="plan-body">
              <div class="plan-content">{{ p.content || `目标 #${p.target_id}` }}</div>
              <div class="plan-meta">间隔 {{ p.interval_days }} 天 · 下次 {{ p.next_review_at.slice(0, 16).replace('T', ' ') }}</div>
            </div>
            <div class="plan-actions">
              <el-button size="small" type="success" plain @click="reviewPlan(p, true)">记住了✓</el-button>
              <el-button size="small" type="danger" plain @click="reviewPlan(p, false)">忘了</el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>📝 错题本</template>
          <el-empty v-if="!wrongs.length" description="暂无错题记录" :image-size="60" />
          <el-table v-else :data="wrongs" size="small" max-height="420">
            <el-table-column prop="question_text" label="题目" min-width="140" show-overflow-tooltip />
            <el-table-column prop="error_type" label="错误类型" width="100" />
            <el-table-column prop="analysis" label="分析" min-width="120" show-overflow-tooltip />
            <el-table-column label="状态" width="70">
              <template #default="{ row }">
                <el-tag size="small" :type="row.mastered ? 'success' : 'danger'">{{ row.mastered ? '已掌握' : '未掌握' }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { eduApi, type ReviewPlan, type WrongQuestion, type StudentProfile } from '../api/edu'
import { useStudentStore } from '../stores/student'

const store = useStudentStore()
const studentId = ref<number | null>(null)
const plans = ref<ReviewPlan[]>([])
const wrongs = ref<WrongQuestion[]>([])
const profile = ref<StudentProfile | null>(null)

async function load() {
  await loadReport()
  if (!studentId.value) return
  ;[plans.value, wrongs.value, profile.value] = await Promise.all([
    eduApi.getReviewPlans(studentId.value),
    eduApi.getWrongQuestions(studentId.value),
    eduApi.getProfile(studentId.value),
  ])
}

async function reviewPlan(p: ReviewPlan, success: boolean) {
  await eduApi.reviewMemory(p.target_id, success)
  ElMessage.success(success ? '已确认记住，下次间隔翻倍' : '已标记遗忘，间隔重置')
  await load()
}

onMounted(async () => {
  await store.loadStudents()
  if (store.students.length) {
    studentId.value = store.students[0].id
    await load()
  }
})
</script>

<style scoped>
.row-between { display: flex; justify-content: space-between; align-items: center; }
.plan-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #f0f2f5; }
.plan-body { flex: 1; min-width: 0; }
.plan-content { font-size: 14px; color: #303133; }
.plan-meta { font-size: 12px; color: #c0c4cc; margin-top: 2px; }
.plan-actions { display: flex; gap: 4px; }
</style>