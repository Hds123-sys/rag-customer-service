import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { isAuthenticated } from './store/auth'
import ChatInterface from './components/ChatInterface.vue'
import DocumentManager from './components/DocumentManager.vue'
import Login from './components/Login.vue'
import Register from './components/Register.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: { requiresAuth: false, title: '注册' },
  },
  {
    path: '/',
    name: 'Chat',
    component: ChatInterface,
    meta: { requiresAuth: true, title: '智能问答' },
  },
  {
    path: '/documents',
    name: 'Documents',
    component: DocumentManager,
    meta: { requiresAuth: true, title: '文档管理' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
let notified = false
router.beforeEach((to, _from, next) => {
  const authenticated = isAuthenticated()

  if (to.meta.requiresAuth && !authenticated) {
    if (!notified) {
      ElMessage.warning('请先登录')
      notified = true
      setTimeout(() => { notified = false }, 1500)
    }
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  if ((to.path === '/login' || to.path === '/register') && authenticated) {
    next('/')
    return
  }

  document.title = to.meta.title ? `${to.meta.title} - 智能客服RAG系统` : '智能客服RAG系统'
  next()
})

export default router