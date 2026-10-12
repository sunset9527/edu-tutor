<template>
  <div class="mem-page">
    <el-card shadow="never" class="top-card">
      <div class="row-between">
        <div class="row-between" style="gap: 12px">
          <el-select v-model="studentId" placeholder="选择学生" style="width: 200px" @change="load">
            <el-option v-for="s in store.students" :key="s.id" :label="`${s.name}（${s.grade}）`" :value="s.id" />
          </el-select>
          <el-tag v-if="store.current" effect="plain" type="info">记忆 {{ total }} 条</el-tag>
        </div>
        <span class="curve-tip">遗忘曲线：R = strength × e^(-λt)，当前 λ={{ decayLambda }}</span>
      </div>
    </el-card>

    <el-row :gutter="12" class="fill-row">
      <el-col :span="10" class="fill-col">
        <el-card shadow="never" class="fill-card">
          <template #header>📉 当前记忆保留率预测</template>
          <v-chart class="curve-chart" :option="curveOption" autoresize />
          <p class="curve-desc">每条曲线从真实强度和最近复习/创建时间起算，横轴为从今天开始的天数。</p>
        </el-card>
      </el-col>
      <el-col :span="14" class="fill-col">
        <el-card shadow="never" class="fill-card">
          <template #header>
            <div class="row-between">
              <span>🧠 记忆库</span>
              <el-radio-group v-model="filter" size="small" @change="onFilterChange">
                <el-radio-button label="all">全部</el-radio-button>
                <el-radio-button label="semantic">画像</el-radio-button>
                <el-radio-button label="episodic">情景</el-radio-button>
                <el-radio-button label="procedural">策略</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <el-scrollbar class="fill-scroll">
            <div v-for="mem in memories" :key="mem.id" class="mem-row">
              <el-tag size="small" :type="typeColor(mem.memory_type)">{{ typeLabel(mem.memory_type) }}</el-tag>
              <div class="mem-row-body">
                <div class="mem-row-content">{{ mem.content }}</div>
                <el-progress :percentage="Math.round(mem.strength * 100)" :stroke-width="6" :show-text="false" style="margin: 4px 0" />
                <span class="mem-meta">强度 {{ mem.strength.toFixed(2) }} · 置信 {{ (mem.confidence * 100).toFixed(0) }}% · {{ mem.created_at?.slice(0, 10) }}</span>
              </div>
              <div class="mem-actions">
                <el-button size="small" type="success" plain @click="review(mem, true)">复习✓</el-button>
                <el-button size="small" plain @click="review(mem, false)">遗忘</el-button>
                <el-button size="small" type="primary" text @click="openEdit(mem)">编辑</el-button>
                <el-button size="small" type="danger" text @click="remove(mem)">删除</el-button>
              </div>
            </div>
            <el-empty v-if="!memories.length" description="暂无记忆" />
          </el-scrollbar>
          <el-pagination
            v-if="total > pageSize"
            v-model:current-page="page"
            :page-size="pageSize"
            :total="total"
            layout="prev, pager, next"
            small
            @current-change="load"
          />
        </el-card>
      </el-col>
    </el-row>
    <el-dialog v-model="editVisible" title="编辑记忆" width="480px">
      <el-input v-model="editContent" type="textarea" :rows="4" />
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { eduApi, type MemoryItem } from '../api/edu'
import { useStudentStore } from '../stores/student'

use([CanvasRenderer, LineChart, TooltipComponent, LegendComponent, GridComponent])

const store = useStudentStore()
const studentId = ref<number | null>(null)
const memories = ref<MemoryItem[]>([])
const filter = ref('all')
const total = ref(0)
const page = ref(1)
const pageSize = 20
const decayLambda = ref(0.1)

const curveOption = computed(() => {
  const days = Array.from({ length: 31 }, (_, i) => i)
  const now = Date.now()
  const series = memories.value.slice(0, 8).map((memory) => {
    const rawBase = memory.last_reviewed_at || memory.created_at
    const base = rawBase ? new Date(rawBase).getTime() : now
    const ageDays = Math.max(0, (now - base) / 86_400_000)
    return {
      name: `#${memory.id} ${memory.content.slice(0, 12)}`,
      type: 'line',
      smooth: true,
      data: days.map((d) => Number((memory.strength * Math.exp(-decayLambda.value * (ageDays + d))).toFixed(3))),
    }
  })
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 40, right: 16, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: days, name: '天数' },
    yAxis: { type: 'value', name: '保留率', max: 1 },
    series,
  }
})

function typeLabel(t: string) {
  return t === 'semantic' ? '画像' : t === 'episodic' ? '情景' : '策略'
}
function typeColor(t: string) {
  return t === 'semantic' ? 'success' : t === 'episodic' ? 'primary' : 'warning'
}

async function load() {
  if (!studentId.value) return
  const result = await eduApi.getMemories(studentId.value, {
    memory_type: filter.value === 'all' ? undefined : filter.value,
    page: page.value,
    page_size: pageSize,
  })
  memories.value = result.items
  total.value = result.total
}

function onFilterChange() {
  page.value = 1
  load()
}

const editing = ref<MemoryItem | null>(null)
const editContent = ref('')
const editVisible = ref(false)

function openEdit(mem: MemoryItem) {
  editing.value = mem
  editContent.value = mem.content
  editVisible.value = true
}

async function saveEdit() {
  if (!editing.value) return
  await eduApi.updateMemory(editing.value.id, { content: editContent.value })
  editVisible.value = false
  ElMessage.success('记忆已更新')
  await load()
}

async function remove(mem: MemoryItem) {
  await eduApi.deleteMemory(mem.id)
  ElMessage.success('记忆已删除（归档）')
  await load()
}

async function review(mem: MemoryItem, success: boolean) {
  await eduApi.reviewMemory(mem.id, success)
  ElMessage.success(success ? '复习成功，强度上升，间隔翻倍' : '已标记遗忘，强度减半')
  await load()
}

onMounted(async () => {
  const [, settings] = await Promise.all([store.loadStudents(), eduApi.getSettings()])
  decayLambda.value = Number(settings.decay_lambda ?? 0.1)
  if (store.students.length) {
    studentId.value = store.students[0].id
    await load()
  }
})
</script>

<style scoped>
.mem-page { height: 100%; display: flex; flex-direction: column; }
.top-card { flex-shrink: 0; margin-bottom: 12px; }
.fill-row { flex: 1; min-height: 0; }
.fill-col { height: 100%; }
.fill-card { height: 100%; display: flex; flex-direction: column; }
.fill-card :deep(.el-card__body) { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }
.fill-scroll { flex: 1; min-height: 0; }
.row-between { display: flex; justify-content: space-between; align-items: center; }
.curve-tip { color: #909399; font-size: 12px; }
.curve-chart { flex: 1; min-height: 300px; }
.curve-desc { color: #909399; font-size: 12px; margin-top: 8px; flex-shrink: 0; }
.mem-row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid #f0f2f5; }
.mem-row-body { flex: 1; min-width: 0; }
.mem-row-content { font-size: 14px; color: #303133; word-break: break-word; }
.mem-meta { font-size: 12px; color: #c0c4cc; }
.mem-actions { display: flex; flex-direction: column; gap: 4px; }
</style>
