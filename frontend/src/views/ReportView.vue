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

    <el-card shadow="never" style="margin-bottom: 12px">
      <template #header>📈 真实学习事件趋势</template>
      <el-empty v-if="!report?.timeline.length" description="v1.6 启用后尚无学习事件" :image-size="60" />
      <v-chart v-else class="timeline-chart" :option="timelineOption" autoresize />
      <div v-if="report?.timeline.length" class="trace-tip">图中每个点都保留对应 learning_events 记录 ID，可回查数据库。</div>
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
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import {
  eduApi,
  type ReviewPlan,
  type StudentReport,
  type WrongQuestion,
  type StudentProfile,
} from '../api/edu'
import { useStudentStore } from '../stores/student'

use([CanvasRenderer, BarChart, LineChart, TooltipComponent, LegendComponent, GridComponent])

const store = useStudentStore()
const studentId = ref<number | null>(null)
const report = ref<StudentReport | null>(null)
const plans = ref<ReviewPlan[]>([])
const wrongs = ref<WrongQuestion[]>([])
const profile = ref<StudentProfile | null>(null)

const timelineOption = computed(() => {
  const points = report.value?.timeline || []
  return {
    tooltip: {
      trigger: 'axis',
      formatter(params: any[]) {
        const index = params[0]?.dataIndex ?? 0
        const point = points[index]
        const lines = params.map((item) => `${item.marker}${item.seriesName}：${item.value ?? '-'}`)
        return [`日期：${point?.date}`, ...lines, `事件 ID：${point?.event_ids.join(', ')}`].join('<br/>')
      },
    },
    legend: { top: 0 },
    grid: { left: 45, right: 45, top: 42, bottom: 28 },
    xAxis: { type: 'category', data: points.map((point) => point.date) },
    yAxis: [
      { type: 'value', name: '事件数', minInterval: 1 },
      { type: 'value', name: '复习完成率', min: 0, max: 1 },
    ],
    series: [
      { name: '掌握度变化', type: 'bar', data: points.map((p) => p.mastery_changes) },
      { name: '新增错题', type: 'bar', data: points.map((p) => p.wrong_added) },
      { name: '掌握错题', type: 'bar', data: points.map((p) => p.wrong_mastered) },
      {
        name: '复习完成率',
        type: 'line',
        yAxisIndex: 1,
        connectNulls: false,
        data: points.map((p) => p.review_completion_rate),
      },
    ],
  }
})

async function load() {
  if (!studentId.value) return
  ;[report.value, plans.value, wrongs.value, profile.value] = await Promise.all([
    eduApi.getReport(studentId.value),
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
.timeline-chart { height: 300px; }
.trace-tip { color: #909399; font-size: 12px; margin-top: 6px; }
</style>
