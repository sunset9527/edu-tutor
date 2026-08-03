<template>
  <div class="settings-page">
    <el-card shadow="never" style="max-width: 560px">
      <template #header>⚙️ 系统参数（保存后立即生效）</template>
      <el-form label-width="150px">
        <el-form-item label="遗忘速率 λ">
          <el-input-number v-model="form.decay_lambda" :min="0.01" :max="0.5" :step="0.01" />
          <div class="form-tip">越大忘得越快（默认 0.1）</div>
        </el-form-item>
        <el-form-item label="首次复习间隔（天）">
          <el-input-number v-model="form.review_interval_base" :min="1" :max="14" />
          <div class="form-tip">记忆创建后多久首次安排复习（默认 1 天）</div>
        </el-form-item>
        <el-form-item label="整合触发阈值">
          <el-input-number v-model="form.consolidation_threshold" :min="1" :max="10" />
          <div class="form-tip">同一知识点出现次数达到该值触发整合（默认 3）</div>
        </el-form-item>
        <el-form-item label="提取置信度下限">
          <el-input-number v-model="form.extract_min_confidence" :min="0" :max="1" :step="0.05" />
          <div class="form-tip">低于该置信度的记忆丢弃（默认 0.5，调高更精准）</div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">保存参数</el-button>
          <el-button @click="load">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { eduApi } from '../api/edu'

const form = ref({ decay_lambda: 0.1, review_interval_base: 1, consolidation_threshold: 3, extract_min_confidence: 0.5 })
const saving = ref(false)

async function load() {
  form.value = await eduApi.getSettings()
}

async function save() {
  saving.value = true
  try {
    await eduApi.updateSettings(form.value)
    ElMessage.success('参数已保存并生效')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.form-tip { color: #c0c4cc; font-size: 12px; line-height: 1.6; }
</style>