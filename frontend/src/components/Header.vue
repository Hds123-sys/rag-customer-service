<template>
  <el-header class="app-header" height="64px">
    <el-space :size="12">
      <el-icon size="28" color="#ffffff"><Service /></el-icon>
      <span class="app-title">智能客服RAG系统</span>
    </el-space>

    <div v-if="user">
      <el-dropdown @command="handleUserAction">
        <div class="user-dropdown">
          <el-space :size="8">
            <el-icon size="20" color="#ffffff"><User /></el-icon>
            <span class="user-name">{{ user.username }}</span>
            <el-icon size="14" color="#ffffff"><ArrowDown /></el-icon>
          </el-space>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <el-icon><Message /></el-icon>
              {{ user.email }}
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <el-icon><SwitchButton /></el-icon>
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </el-header>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Message, Service, SwitchButton, User } from '@element-plus/icons-vue'
import auth from '../services/auth'
import { authState } from '../store/auth'

const router = useRouter()
const user = computed(() => authState.user)

const handleUserAction = async (command) => {
  if (command !== 'logout') return

  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (error) {
    return // 用户取消
  }

  try {
    await auth.logout()
  } catch (error) {
    // 退出接口失败不影响本地登出
  }

  // 先清理登录态, 再跳转; 组件内部也会在无 Token 时跳过请求
  auth.removeToken()
  ElMessage.success('已退出登录')
  try {
    await router.push('/login')
  } catch (error) {
    window.location.href = '/login'
  }
}
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.app-title {
  color: #ffffff;
  font-size: 18px;
  font-weight: 600;
}

.user-dropdown {
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.3s;
}

.user-dropdown:hover {
  background: rgba(255, 255, 255, 0.15);
}

.user-name {
  color: #ffffff;
}
</style>