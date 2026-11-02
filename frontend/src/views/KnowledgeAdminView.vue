<template>
  <section class="governance-page" aria-labelledby="governance-title">
    <header class="page-header">
      <div>
        <h1 id="governance-title">教材治理</h1>
        <p>上传、构建、审核和纠错均保留可追溯记录；只有通过审核的版本才能激活。</p>
      </div>
      <el-button :loading="loading" aria-label="刷新教材治理数据" @click="loadAll">刷新数据</el-button>
    </header>

    <div class="summary-grid" aria-label="教材治理概览">
      <el-card shadow="never"><span>教材</span><strong>{{ textbooks.length }}</strong></el-card>
      <el-card shadow="never"><span>构建任务</span><strong>{{ builds.length }}</strong></el-card>
      <el-card shadow="never"><span>需要处理</span><strong>{{ attentionBuilds }}</strong></el-card>
      <el-card shadow="never"><span>待审核纠错</span><strong>{{ pendingCorrections }}</strong></el-card>
    </div>

    <el-tabs v-model="activeTab" class="governance-tabs">
      <el-tab-pane label="教材" name="textbooks">
        <div class="tab-grid">
          <el-card class="upload-card" shadow="never">
            <template #header>上传教材 PDF</template>
            <el-alert title="仅上传拥有合法来源和授权说明的 PDF；系统会校验文件头、页数与哈希。" type="info" :closable="false" show-icon />
            <el-form class="upload-form" label-position="top" @submit.prevent>
              <el-form-item label="PDF 文件" required :error="uploadError">
                <input aria-label="PDF 文件" type="file" accept="application/pdf,.pdf" @change="onFileChange" />
              </el-form-item>
              <div class="form-columns">
                <el-form-item label="学段" required><el-input v-model="upload.school_stage" placeholder="如：初中" /></el-form-item>
                <el-form-item label="年级" required><el-input v-model="upload.grade" placeholder="如：七年级" /></el-form-item>
                <el-form-item label="学科" required><el-input v-model="upload.subject" placeholder="如：数学" /></el-form-item>
                <el-form-item label="册次" required><el-input v-model="upload.volume" placeholder="如：上册" /></el-form-item>
                <el-form-item label="出版社" required><el-input v-model="upload.publisher" /></el-form-item>
                <el-form-item label="版次" required><el-input v-model="upload.edition" /></el-form-item>
              </div>
              <el-form-item label="来源说明" required><el-input v-model="upload.source_note" type="textarea" :rows="2" /></el-form-item>
              <el-form-item label="授权说明" required><el-input v-model="upload.license_note" type="textarea" :rows="2" /></el-form-item>
              <el-button type="primary" native-type="submit" :loading="uploading" :disabled="!selectedFile" @click="submitUpload">上传并登记</el-button>
            </el-form>
          </el-card>

          <el-card shadow="never" class="table-card">
            <template #header>已登记教材</template>
            <el-empty v-if="!textbooks.length && !loading" description="还没有教材，先在左侧登记第一册 PDF。" />
            <el-table v-else :data="textbooks" max-height="470" aria-label="已登记教材列表">
              <el-table-column label="教材" min-width="180">
                <template #default="{ row }"><strong>{{ row.subject }} · {{ row.grade }}</strong><br><small>{{ row.publisher }} · {{ row.edition }} · {{ row.volume }}</small></template>
              </el-table-column>
              <el-table-column label="页数" width="76"><template #default="{ row }">{{ row.page_count ?? '—' }}</template></el-table-column>
              <el-table-column label="当前版本" width="100"><template #default="{ row }">{{ row.active_version_id ? `v${row.active_version_id}` : '未激活' }}</template></el-table-column>
              <el-table-column label="哈希" min-width="100"><template #default="{ row }"><code>{{ shortHash(row.file_sha256) }}</code></template></el-table-column>
              <el-table-column label="操作" width="120" fixed="right">
                <template #default="{ row }"><el-button size="small" type="primary" :loading="busyKey === `build-${row.id}`" @click="createBuild(row.id)">开始构建</el-button></template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane label="构建任务" name="builds">
        <el-card shadow="never">
          <template #header><div class="card-heading"><span>构建进度与可恢复操作</span><small>任务停止或失败时不会被伪装为完成。</small></div></template>
          <el-empty v-if="!builds.length && !loading" description="暂无构建任务。请先上传教材，再创建构建任务。" />
          <el-table v-else :data="builds" max-height="530" aria-label="教材构建任务列表">
            <el-table-column prop="id" label="任务" width="76" />
            <el-table-column label="状态" min-width="135"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ buildStatusText(row.status) }}</el-tag><br><small>{{ row.stage }}</small></template></el-table-column>
            <el-table-column label="进度" min-width="185"><template #default="{ row }"><el-progress :percentage="buildProgress(row)" :status="row.status === 'succeeded' ? 'success' : row.status === 'needs_attention' ? 'exception' : undefined" /><small>完成 {{ row.completed_units }}/{{ row.total_units }}，失败 {{ row.failed_units }}</small></template></el-table-column>
            <el-table-column label="租约" min-width="150"><template #default="{ row }">{{ row.lease_owner || '未被 worker 认领' }}</template></el-table-column>
            <el-table-column label="恢复操作" min-width="255" fixed="right"><template #default="{ row }"><el-space wrap><el-button size="small" :disabled="!['needs_attention', 'queued', 'running'].includes(row.status)" :loading="busyKey === `resume-${row.id}`" @click="runBuildAction('resume', row.id)">续跑</el-button><el-button size="small" type="warning" :disabled="!row.failed_units" :loading="busyKey === `retry-${row.id}`" @click="runBuildAction('retry', row.id)">重试失败项</el-button><el-button size="small" type="danger" plain :disabled="!['queued', 'running', 'needs_attention'].includes(row.status)" @click="confirmCancel(row.id)">取消</el-button></el-space></template></el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="版本审核" name="versions">
        <div class="tab-grid review-grid">
          <el-card shadow="never">
            <template #header>选择版本并抽检</template>
            <el-form label-position="top">
              <el-form-item label="知识版本"><el-select v-model="selectedVersionId" placeholder="选择构建或激活过的版本" @change="loadVersion"><el-option v-for="id in versionIds" :key="id" :label="`版本 #${id}`" :value="id" /></el-select></el-form-item>
              <el-form-item label="审核结论"><el-radio-group v-model="reviewConclusion"><el-radio value="passed">通过</el-radio><el-radio value="rejected">驳回</el-radio></el-radio-group></el-form-item>
              <el-form-item label="审核说明"><el-input v-model="reviewNote" type="textarea" :rows="3" placeholder="记录抽检范围、问题或通过依据" /></el-form-item>
              <el-button type="primary" :disabled="!selectedVersionId" :loading="busyKey === 'review'" @click="submitReview">提交五项抽检</el-button>
            </el-form>
            <el-alert class="gate-note" title="激活门禁：正文、公式、知识点、难度、先修关系五类抽检均通过，并且双库一致，才可激活。" type="warning" :closable="false" show-icon />
          </el-card>
          <el-card shadow="never" class="version-detail">
            <template #header>版本详情</template>
            <el-empty v-if="!versionDetail" description="选择一个版本查看来源、知识点和审核记录。" />
            <template v-else>
              <el-descriptions :column="2" border><el-descriptions-item label="状态"><el-tag :type="statusType(versionDetail.status)">{{ versionDetail.status }}</el-tag></el-descriptions-item><el-descriptions-item label="父版本">{{ versionDetail.parent_version_id || '无' }}</el-descriptions-item><el-descriptions-item label="知识点">{{ versionDetail.point_count }}</el-descriptions-item><el-descriptions-item label="来源块">{{ versionDetail.source_chunk_count }}</el-descriptions-item></el-descriptions>
              <h3>抽样知识点</h3>
              <el-table :data="versionDetail.points.slice(0, 8)" size="small" max-height="180"><el-table-column prop="title" label="标题" /><el-table-column prop="difficulty" label="难度" width="88" /><el-table-column label="来源缺口" width="100"><template #default="{ row }">{{ row.provenance_gap ? 'legacy 缺口' : '完整' }}</template></el-table-column></el-table>
              <div class="version-actions"><el-button type="success" :loading="busyKey === 'activate'" @click="confirmActivate">激活此版本</el-button><el-button @click="confirmRollback">回滚到此版本</el-button></div>
            </template>
          </el-card>
        </div>
      </el-tab-pane>

      <el-tab-pane label="纠错队列" name="corrections">
        <el-card shadow="never">
          <template #header><div class="queue-filters"><span>等待管理员处理的反馈</span><el-select v-model="correctionStatus" clearable placeholder="全部状态" @change="loadCorrections"><el-option label="待处理" value="pending" /><el-option label="已接受" value="accepted" /><el-option label="已应用" value="applied" /><el-option label="已驳回" value="rejected" /></el-select></div></template>
          <el-empty v-if="!corrections.length && !loading" description="当前没有纠错工单。" />
          <el-table v-else :data="corrections" max-height="530" aria-label="纠错工单列表">
            <el-table-column prop="id" label="工单" width="75" />
            <el-table-column label="类型 / 状态" width="145"><template #default="{ row }"><span>{{ categoryText(row.category) }}</span><br><el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template></el-table-column>
            <el-table-column prop="reason" label="反馈原因" min-width="180" show-overflow-tooltip />
            <el-table-column label="建议值" min-width="180"><template #default="{ row }"><code class="json-preview">{{ stringify(row.proposed_value) }}</code></template></el-table-column>
            <el-table-column label="操作" width="190" fixed="right"><template #default="{ row }"><el-space v-if="row.status === 'pending'"><el-button size="small" type="success" :loading="busyKey === `accept-${row.id}`" @click="handleTicket(row.id, 'accept')">接受</el-button><el-button size="small" type="danger" plain @click="handleTicket(row.id, 'reject')">驳回</el-button></el-space><span v-else>{{ row.handling_note || '已处理' }}</span></template></el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { governanceApi, type BuildTask, type CorrectionTicket, type KnowledgeVersion, type Textbook } from '../api/governance'

const activeTab = ref('textbooks')
const loading = ref(false)
const uploading = ref(false)
const busyKey = ref('')
const textbooks = ref<Textbook[]>([])
const builds = ref<BuildTask[]>([])
const corrections = ref<CorrectionTicket[]>([])
const correctionStatus = ref('')
const selectedFile = ref<File | null>(null)
const uploadError = ref('')
const selectedVersionId = ref<number | null>(null)
const versionDetail = ref<KnowledgeVersion | null>(null)
const reviewConclusion = ref<'passed' | 'rejected'>('passed')
const reviewNote = ref('')
const upload = reactive({ school_stage: '', grade: '', subject: '', publisher: '', edition: '', volume: '', source_note: '', license_note: '' })

const attentionBuilds = computed(() => builds.value.filter((row) => row.status === 'needs_attention').length)
const pendingCorrections = computed(() => corrections.value.filter((row) => row.status === 'pending').length)
const versionIds = computed(() => [...new Set([
  ...textbooks.value.map((row) => row.active_version_id).filter((id): id is number => Boolean(id)),
  ...builds.value.map((row) => row.target_version_id).filter((id): id is number => Boolean(id)),
])].sort((a, b) => b - a))

function errorText(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : '请求失败，请检查状态后重试。'
}
function shortHash(value: string) { return value ? `${value.slice(0, 10)}…` : '—' }
function stringify(value: unknown) { return value ? JSON.stringify(value) : '—' }
function buildProgress(row: BuildTask) { return row.total_units ? Math.round((row.completed_units / row.total_units) * 100) : 0 }
function statusType(status: string) { return ({ succeeded: 'success', active: 'success', staged: 'warning', needs_attention: 'danger', failed: 'danger', rejected: 'danger', pending: 'warning', accepted: 'warning', applied: 'success' } as Record<string, 'success' | 'warning' | 'danger' | 'info'>)[status] || 'info' }
function statusText(status: string) { return ({ pending: '待处理', accepted: '已接受', applied: '已应用', rejected: '已驳回', needs_attention: '需要处理', succeeded: '已完成', queued: '等待执行', running: '执行中', cancelled: '已取消' } as Record<string, string>)[status] || status }
function buildStatusText(status: string) { return statusText(status) }
function categoryText(category: string) { return ({ knowledge: '教材知识', memory: '学生记忆', explanation: '回答讲解', question: '题目' } as Record<string, string>)[category] || category }

async function loadCorrections() {
  const page = await governanceApi.listCorrections(correctionStatus.value ? { status: correctionStatus.value } : undefined)
  corrections.value = page.items
}
async function loadAll() {
  loading.value = true
  try {
    const [textbookPage, buildPage] = await Promise.all([governanceApi.listTextbooks(), governanceApi.listBuilds(), loadCorrections()])
    textbooks.value = textbookPage.items
    builds.value = buildPage.items
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally { loading.value = false }
}
function validateUploadFile(file: File) {
  if (!file.name.toLowerCase().endsWith('.pdf') || file.type && file.type !== 'application/pdf') {
    uploadError.value = '请选择 PDF 文件。'
    return false
  }
  uploadError.value = ''
  return true
}
function onFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] || null
  selectedFile.value = file && validateUploadFile(file) ? file : null
}
async function submitUpload() {
  if (!selectedFile.value || !validateUploadFile(selectedFile.value)) return
  const missing = Object.values(upload).some((value) => !value.trim())
  if (missing) { uploadError.value = '请完整填写教材来源与授权信息。'; return }
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    Object.entries(upload).forEach(([key, value]) => form.append(key, value.trim()))
    await governanceApi.uploadTextbook(form)
    ElMessage.success('教材已登记，可以创建构建任务。')
    selectedFile.value = null
    await loadAll()
  } catch (error) { uploadError.value = errorText(error) } finally { uploading.value = false }
}
async function createBuild(textbookId: number) {
  busyKey.value = `build-${textbookId}`
  try { await governanceApi.createBuild(textbookId, { group_size: 12, use_ocr: false }); ElMessage.success('已创建构建任务。'); await loadAll() } catch (error) { ElMessage.error(errorText(error)) } finally { busyKey.value = '' }
}
async function runBuildAction(action: 'resume' | 'retry', taskId: number) {
  busyKey.value = `${action}-${taskId}`
  try { if (action === 'resume') await governanceApi.resumeBuild(taskId); else await governanceApi.retryFailures(taskId); ElMessage.success(action === 'resume' ? '任务已续跑。' : '失败单元已重置等待重试。'); await loadAll() } catch (error) { ElMessage.error(errorText(error)) } finally { busyKey.value = '' }
}
async function confirmCancel(taskId: number) {
  try { await ElMessageBox.confirm('取消只会停止未完成单元，已生成数据会保留用于审计。', '确认取消构建', { type: 'warning', confirmButtonText: '确认取消' }); await governanceApi.cancelBuild(taskId); await loadAll() } catch { /* 用户取消或请求失败时保持当前界面 */ }
}
async function loadVersion() {
  if (!selectedVersionId.value) return
  try { versionDetail.value = await governanceApi.getVersion(selectedVersionId.value) } catch (error) { ElMessage.error(errorText(error)) }
}
async function submitReview() {
  if (!selectedVersionId.value) return
  busyKey.value = 'review'
  try {
    await governanceApi.reviewVersion(selectedVersionId.value, { conclusion: reviewConclusion.value, note: reviewNote.value || null, items: ['content', 'formula', 'knowledge_point', 'difficulty', 'prerequisite'].map((item_type) => ({ item_type, target_type: 'version', conclusion: reviewConclusion.value === 'passed' ? 'pass' : 'fail' })) })
    ElMessage.success('审核记录已保存。'); await loadVersion()
  } catch (error) { ElMessage.error(errorText(error)) } finally { busyKey.value = '' }
}
async function confirmActivate() {
  if (!versionDetail.value) return
  const textbook = textbooks.value.find((row) => row.id === versionDetail.value?.textbook_id)
  try { await ElMessageBox.confirm('激活会切换当前教材版本；历史版本仍可用于审计和回滚。', '确认激活版本', { type: 'warning', confirmButtonText: '确认激活' }); busyKey.value = 'activate'; await governanceApi.activateVersion(versionDetail.value.id, textbook?.active_version_id ?? null); ElMessage.success('版本已激活。'); await loadAll(); await loadVersion() } catch (error) { if (error !== 'cancel') ElMessage.error(errorText(error)) } finally { busyKey.value = '' }
}
async function confirmRollback() {
  if (!versionDetail.value) return
  const textbook = textbooks.value.find((row) => row.id === versionDetail.value?.textbook_id)
  if (!textbook) return
  try { await ElMessageBox.confirm('回滚会切换 active 指针，不删除任何历史版本或向量。', '确认回滚版本', { type: 'warning', confirmButtonText: '确认回滚' }); await governanceApi.rollbackTextbook(textbook.id, versionDetail.value.id, textbook.active_version_id ?? null); ElMessage.success('已切回目标版本。'); await loadAll(); await loadVersion() } catch (error) { if (error !== 'cancel') ElMessage.error(errorText(error)) }
}
async function handleTicket(ticketId: number, action: 'accept' | 'reject') {
  try {
    const result = await ElMessageBox.prompt(action === 'accept' ? '请填写接受与处理说明。' : '驳回必须说明原因。', action === 'accept' ? '接受纠错' : '驳回纠错', { inputPattern: /\S+/, inputErrorMessage: '处理说明不能为空', confirmButtonText: '提交' })
    busyKey.value = `${action}-${ticketId}`
    if (action === 'accept') await governanceApi.acceptCorrection(ticketId, result.value)
    else await governanceApi.rejectCorrection(ticketId, result.value)
    ElMessage.success('工单已更新。'); await loadCorrections()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorText(error)) } finally { busyKey.value = '' }
}

onMounted(loadAll)
</script>

<style scoped>
.governance-page { width: 100%; min-width: 0; overflow: auto; padding: 4px; color: #303133; }
.page-header { display: flex; justify-content: space-between; align-items: start; gap: 16px; margin: 4px 0 18px; }
.page-header h1 { font-size: 24px; line-height: 1.3; margin: 0; }
.page-header p { color: #606266; line-height: 1.55; margin-top: 6px; max-width: 720px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.summary-grid :deep(.el-card__body) { display: flex; flex-direction: column; gap: 6px; min-height: 76px; padding: 14px 16px; }
.summary-grid span, small { color: #606266; font-size: 12px; }
.summary-grid strong { color: #303133; font-size: 25px; font-variant-numeric: tabular-nums; }
.tab-grid { display: grid; grid-template-columns: minmax(310px, .9fr) minmax(0, 1.4fr); gap: 16px; align-items: start; }
.upload-card :deep(.el-card__body), .table-card :deep(.el-card__body) { min-width: 0; }
.upload-form { margin-top: 14px; }
.form-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; }
.form-columns :deep(.el-form-item) { min-width: 0; }
.card-heading, .queue-filters { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.gate-note { margin-top: 16px; }
.review-grid { grid-template-columns: minmax(290px, .75fr) minmax(0, 1.5fr); }
.version-detail h3 { font-size: 14px; margin: 18px 0 9px; }
.version-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.json-preview { display: block; max-width: 210px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #606266; }
.el-button { min-height: 36px; }
@media (max-width: 900px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .tab-grid { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .governance-page { padding: 0; } .page-header { align-items: stretch; flex-direction: column; } .page-header :deep(.el-button) { width: 100%; } .form-columns { grid-template-columns: 1fr; } .summary-grid { gap: 8px; } .queue-filters { align-items: stretch; flex-direction: column; } .queue-filters :deep(.el-select) { width: 100%; } }
</style>
