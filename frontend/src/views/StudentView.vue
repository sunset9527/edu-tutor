<template>
  <div class="student-page">
    <el-row :gutter="16" class="fill-row">
      <el-col :span="8" class="fill-col">
        <el-card shadow="never" class="fill-card">
          <template #header>
            <div class="row-between">
              <span>学生列表</span>
              <el-button type="primary" size="small" @click="dialogVisible = true">+ 新建</el-button>
            </div>
          </template>
          <el-scrollbar class="fill-scroll">
            <el-menu :default-active="selectedId?.toString()" @select="select">
              <el-menu-item v-for="s in students" :key="s.id" :index="s.id.toString()">
                {{ s.name }}（{{ s.grade }}·{{ s.subject }}）
              </el-menu-item>
            </el-menu>
          </el-scrollbar>
        </el-card>
      </el-col>

      <el-col :span="16" class="fill-col">
        <el-card v-if="profile" shadow="never" class="fill-card">
          <template #header>
            <div class="row-between">
              <span class="profile-title">{{ profile.name }} 的学习画像</span>
              <el-tag type="info" effect="plain">{{ profile.level }}</el-tag>
            </div>
          </template>
          <el-row :gutter="16" class="fill-row">
            <el-col :span="12" class="fill-col">
              <div class="tag-section">
                <div class="tag-title">⚠️ 薄弱点（{{ profile.weaknesses.length }}）</div>
                <div v-if="!profile.weaknesses.length" class="empty-text">暂无，继续保持</div>
                <el-tag v-for="w in profile.weaknesses" :key="w" type="danger" class="tag-item">{{ w }}</el-tag>
              </div>
              <div class="tag-section">
                <div class="tag-title">✅ 已掌握（{{ profile.strengths.length }}）</div>
                <div v-if="!profile.strengths.length" class="empty-text">暂无</div>
                <el-tag v-for="s in profile.strengths" :key="s" type="success" class="tag-item">{{ s }}</el-tag>
              </div>
            </el-col>
            <el-col :span="12" class="fill-col">
              <v-chart class="radar-chart" :option="radarOption" autoresize />
            </el-col>
          </el-row>
        </el-card>
        <el-empty v-else description="请选择学生查看画像" />
      </el-col>
    </el-row>

    <el-dialog v-model="dialogVisible" title="新建学生" width="420px">
      <el-form label-width="70px">
        <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="年级"><el-input v-model="form.grade" placeholder="初一" /></el-form-item>
        <el-form-item label="科目"><el-input v-model="form.subject" placeholder="数学" /></el-form-item>
        <el-form-item label="水平">
          <el-select v-model="form.level">
            <el-option label="入门" value="入门" />
            <el-option label="基础" value="基础" />
            <el-option label="中等" value="中等" />
            <el-option label="进阶" value="进阶" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { eduApi, type Student, type StudentProfile } from '../api/edu'
import { useStudentStore } from '../stores/student'

use([CanvasRenderer, RadarChart, TooltipComponent, LegendComponent])

const store = useStudentStore()
const students = ref<Student[]>([])
const selectedId = ref<number | null>(null)
const profile = ref<StudentProfile | null>(null)
const dialogVisible = ref(false)
const form = ref({ name: '', grade: '初一', subject: '数学', level: '基础' })

const radarOption = computed(() => {
  const w = profile.value?.weaknesses?.length ?? 0
  const s = profile.value?.strengths?.length ?? 0
  return {
    title: { text: '学习状态雷达', left: 'center', top: 8, textStyle: { fontSize: 13 } },
    radar: {
      indicator: [
        { name: '薄弱点数', max: 8 },
        { name: '掌握数', max: 8 },
        { name: '画像完整度', max: 10 },
      ],
      radius: '58%',
      center: ['50%', '56%'],
    },
    series: [
      {
        type: 'radar',
        data: [{ value: [Math.min(w, 8), Math.min(s, 8), Math.min(w + s, 10)], name: '当前状态' }],
        areaStyle: { opacity: 0.2 },
      },
    ],
  }
})

async function load() {
  students.value = await eduApi.listStudents()
  if (students.value.length && !selectedId.value) {
    selectedId.value = students.value[0].id
  }
  if (selectedId.value) await loadProfile()
}

async function loadProfile() {
  if (!selectedId.value) return
  profile.value = await eduApi.getProfile(selectedId.value)
}

function select(index: string) {
  selectedId.value = Number(index)
  loadProfile()
}

async function create() {
  if (!form.value.name) return ElMessage.warning('请输入姓名')
  const stu = await eduApi.createStudent(form.value)
  await load()
  selectedId.value = stu.id
  await loadProfile()
  dialogVisible.value = false
  ElMessage.success('学生创建成功')
}

onMounted(load)
</script>

<style scoped>
.student-page { height: 100%; display: flex; flex-direction: column; }
.fill-row { flex: 1; min-height: 0; }
.fill-col { height: 100%; }
.fill-card { height: 100%; display: flex; flex-direction: column; }
.fill-card :deep(.el-card__body) { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }
.fill-scroll { flex: 1; min-height: 0; }
.row-between { display: flex; justify-content: space-between; align-items: center; }
.profile-title { font-weight: 600; font-size: 15px; }
.tag-section { margin-bottom: 16px; }
.tag-title { font-size: 13px; color: #606266; margin-bottom: 8px; font-weight: 600; }
.tag-item { margin: 0 6px 6px 0; }
.empty-text { color: #c0c4cc; font-size: 13px; }
.radar-chart { flex: 1; min-height: 260px; }
</style>