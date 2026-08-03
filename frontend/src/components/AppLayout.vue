<template>
  <el-container class="app-layout">
    <el-aside width="220px" class="app-aside">
      <div class="logo">🎓 EduTutor</div>`n      <div class="user-bar" v-if="auth.user">`n        <span class="user-name">{{ auth.user.username }}</span>`n        <el-button size="small" text type="danger" @click="logout">退出</el-button>`n      </div>
      <el-menu :default-active="activeMenu" router class="app-menu">
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>辅导对话</span>
        </el-menu-item>
        <el-menu-item index="/quiz">
          <el-icon><EditPen /></el-icon>
          <span>智能出题</span>
        </el-menu-item>
        <el-menu-item index="/students">
          <el-icon><User /></el-icon>
          <span>学生管理</span>
        </el-menu-item>
        <el-menu-item index="/memories">
          <el-icon><Memo /></el-icon>
          <span>记忆库</span>
        </el-menu-item>
        <el-menu-item index="/graph">
          <el-icon><Share /></el-icon>
          <span>知识图谱</span>
        </el-menu-item>
        <el-menu-item index="/report">
          <el-icon><DataAnalysis /></el-icon>
          <span>学习报告</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ChatDotRound, User, Memo, Share, DataAnalysis, Setting, EditPen } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const auth = useAuthStore()
const router = useRouter()
function logout() {
  auth.logout()
  router.push('/login')
}
const activeMenu = computed(() => '/' + (route.path.split('/')[1] || 'chat'))
</script>

<style scoped>
.app-layout { height: 100%; }
.app-aside { background: #fff; border-right: 1px solid #e4e7ed; }
.logo { height: 60px; line-height: 60px; text-align: center; font-size: 18px; font-weight: 700; color: #409eff; border-bottom: 1px solid #f0f2f5; }
.app-menu { border-right: none; }
.user-bar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-bottom: 1px solid #f0f2f5; font-size: 13px; }
.user-name { color: #606266; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* 关键：main 变 flex 容器，子页面自动撑满剩余高度，消灭底部空白 */
.app-main { background: #f5f7fa; padding: 16px; overflow: hidden; display: flex; flex-direction: column; }
.app-main > * { flex: 1; min-height: 0; }
</style>