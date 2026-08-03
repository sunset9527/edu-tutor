<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="login-logo">🎓 EduTutor</div>
      <div class="login-sub">智能体记忆增强 · 个性化教育辅导</div>
      <el-tabs v-model="tab" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form label-position="top" @keyup.enter="submit">
            <el-form-item label="用户名">
              <el-input v-model="username" placeholder="请输入用户名" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="password" type="password" show-password placeholder="请输入密码" />
            </el-form-item>
            <el-button type="primary" class="submit-btn" :loading="loading" @click="submit">
              登录
            </el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form label-position="top" @keyup.enter="submit">
            <el-form-item label="用户名">
              <el-input v-model="username" placeholder="至少 2 个字符" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="password" type="password" show-password placeholder="至少 6 个字符" />
            </el-form-item>
            <el-button type="success" class="submit-btn" :loading="loading" @click="submit">
              注册并登录
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const tab = ref('login')
const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (tab.value === 'login') {
      await auth.login(username.value.trim(), password.value)
    } else {
      await auth.register(username.value.trim(), password.value)
    }
    ElMessage.success('欢迎回来，' + auth.user?.username)
    router.push('/chat')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e8f1ff 0%, #f5f7fa 100%);
}
.login-card { width: 380px; padding: 8px 12px; }
.login-logo { text-align: center; font-size: 26px; font-weight: 700; color: #409eff; margin-top: 8px; }
.login-sub { text-align: center; color: #909399; font-size: 13px; margin: 6px 0 18px; }
.submit-btn { width: 100%; margin-top: 4px; }
</style>