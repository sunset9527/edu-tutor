<template>
  <div class="graph-page">
    <el-row :gutter="12" class="fill-row">
      <el-col :span="17" class="fill-col">
        <el-card shadow="never" class="fill-card">
          <template #header>
            <div class="row-between">
              <div class="row-between" style="gap: 12px">
                <el-select v-model="subject" style="width: 110px" @change="load">
                  <el-option v-for="s in subjects" :key="s" :label="s" :value="s" />
                </el-select>
                <span>🕸️ {{ subject }} 知识图谱（{{ graph.nodes.length }} 节点 · {{ graph.edges.length }} 边）</span>
              </div>
              <el-tag type="success" effect="plain">连接率 {{ (connectRate * 100).toFixed(1) }}%</el-tag>
            </div>
          </template>
          <v-chart class="graph-chart" :option="graphOption" autoresize @click="onClick" />
          <div class="legend-tip">
            <el-tag size="small" type="success">基础</el-tag>
            <el-tag size="small" type="warning" style="margin-left: 6px">进阶</el-tag>
            <el-tag size="small" type="danger" style="margin-left: 6px">拔高</el-tag>
            <span style="margin-left: 12px; color: #909399; font-size: 12px">实线=前置关系 · 虚线=相关关系 · 点击节点查看详情</span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="7" class="fill-col">
        <el-card shadow="never" class="fill-card">
          <template #header>📖 知识点详情</template>
          <el-empty v-if="!detail" description="点击图谱中的节点" :image-size="60" />
          <div v-else class="detail-scroll">
            <h3 class="detail-title">{{ detail.title }}</h3>
            <el-tag size="small" :type="difficultyType(detail.difficulty)" style="margin-bottom: 8px">{{ detail.difficulty }}</el-tag>
            <div class="detail-chapter">{{ detail.chapter }}</div>
            <div class="detail-md" v-html="mdToHtml(detail.content_md)"></div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { eduApi, type GraphData } from '../api/edu'

use([CanvasRenderer, GraphChart, TooltipComponent])

const subjects = ['数学', '语文', '生物']
const subject = ref('数学')
const graph = ref<GraphData>({ nodes: [], edges: [] })
const stats = ref<{ connect_rate: number }>({ connect_rate: 0 })
const detail = ref<any>(null)
const learningPath = ref<any[]>([])
const pathLoading = ref(false)

async function showPath(kpId: number) {
  pathLoading.value = true
  try {
    const r = await eduApi.getLearningPath(kpId)
    learningPath.value = r.path
  } catch (e) {
    learningPath.value = []
  } finally {
    pathLoading.value = false
  }
}

async function load() {
  graph.value = await eduApi.getGraph(subject.value)
  stats.value = await eduApi.getKnowledgeStats(subject.value)
  detail.value = null
}

const connectRate = computed(() => stats.value.connect_rate ?? 0)

const graphOption = computed(() => {
  const degreeMap = new Map<number, number>()
  graph.value.edges.forEach((e) => {
    degreeMap.set(e.source, (degreeMap.get(e.source) || 0) + 1)
    degreeMap.set(e.target, (degreeMap.get(e.target) || 0) + 1)
  })
  const nodes = graph.value.nodes.map((n) => ({
    id: n.id,
    name: n.title,
    symbolSize: 14 + Math.min((degreeMap.get(n.id) || 1) * 2, 20),
    itemStyle: {
      color: n.difficulty === '基础' ? '#67c23a' : n.difficulty === '进阶' ? '#e6a23c' : '#f56c6c',
    },
    category: n.difficulty,
  }))
  const links = graph.value.edges.map((e) => ({
    source: e.source,
    target: e.target,
    lineStyle: {
      type: e.type === 'prerequisite' ? 'solid' : 'dashed',
      curveness: 0.1,
    },
  }))
  return {
    tooltip: {},
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        data: nodes,
        links,
        force: { repulsion: 220, edgeLength: 90 },
        label: { show: true, fontSize: 10 },
        emphasis: { focus: 'adjacency' },
      },
    ],
  }
})

function difficultyType(d: string) {
  return d === '基础' ? 'success' : d === '进阶' ? 'warning' : 'danger'
}

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function mdToHtml(s: string) {
  return escapeHtml(s || '')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
    .replace(/\$([^$]+)\$/g, '<code>$1</code>')
}

function onClick(params: any) {
  if (params?.dataType === 'node') {
    eduApi.getKnowledgeDetail(params.data.id).then((d) => (detail.value = d))
  }
}

onMounted(load)
</script>

<style scoped>
.graph-page { height: 100%; display: flex; flex-direction: column; }
.fill-row { flex: 1; min-height: 0; }
.fill-col { height: 100%; }
.fill-card { height: 100%; display: flex; flex-direction: column; }
.fill-card :deep(.el-card__body) { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }
.row-between { display: flex; justify-content: space-between; align-items: center; }
.graph-chart { flex: 1; min-height: 400px; }
.path-box { margin-top: 10px; background: #f8fafc; border-radius: 6px; padding: 10px; }
.path-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.path-step { display: flex; align-items: center; gap: 6px; padding: 4px 0; font-size: 13px; }
.path-step.target { color: #f56c6c; font-weight: 600; }
.path-num { width: 18px; height: 18px; border-radius: 50%; background: #409eff; color: #fff; font-size: 11px; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.legend-tip { margin-top: 8px; flex-shrink: 0; }
.detail-scroll { overflow-y: auto; }
.detail-title { font-size: 16px; margin-bottom: 6px; }
.detail-chapter { color: #909399; font-size: 12px; margin-bottom: 10px; }
.detail-md { font-size: 13px; line-height: 1.8; color: #303133; word-break: break-word; }
</style>