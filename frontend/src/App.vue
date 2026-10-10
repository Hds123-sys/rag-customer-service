<template>
  <el-container v-if="authenticated" class="app-shell" direction="vertical">
    <AppHeader />

    <el-container class="app-body">
      <el-aside width="220px" class="app-aside">
        <el-menu :default-active="activeMenu" class="app-menu" router>
          <el-menu-item index="/">
            <el-icon><ChatLineSquare /></el-icon>
            <span>智能问答</span>
          </el-menu-item>
          <el-menu-item index="/documents">
            <el-icon><Document /></el-icon>
            <span>文档管理</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <router-view v-else />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { authState } from './store/auth'
import AppHeader from './components/Header.vue'

const route = useRoute()
const authenticated = computed(() => Boolean(authState.token))
const activeMenu = computed(() => (route.path === '/documents' ? '/documents' : '/'))
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
}

.app-body {
  height: calc(100vh - 64px);
}

.app-aside {
  background: #ffffff;
  border-right: 1px solid #ebeef5;
  padding-top: 12px;
}

.app-menu {
  border-right: none;
}

.app-main {
  padding: 0;
  background: #f5f7fa;
  overflow: hidden;
}

/* 窄窗口(例如内置浏览器侧栏)下把侧边栏收成图标, 把宽度让给内容区 */
@media (max-width: 820px) {
  .app-aside {
    width: 64px !important;
  }

  :deep(.app-menu .el-menu-item) {
    padding-left: 20px !important;
    padding-right: 20px !important;
  }

  :deep(.app-menu .el-menu-item span) {
    display: none;
  }
}
</style>