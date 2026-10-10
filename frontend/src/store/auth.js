/**
 * 全局登录状态(响应式)
 *
 * 持久化策略:
 * - 登录时勾选「记住我」: 写入 localStorage, 关闭浏览器后仍然保持登录
 * - 未勾选: 写入 sessionStorage, 关闭标签页后自动失效
 *
 * 读取时优先 sessionStorage, 再回退 localStorage, 两种方式都能恢复登录态。
 */
import { reactive } from 'vue'

const TOKEN_KEY = 'access_token'
const USER_KEY = 'user_info'

function safeGet(storage, key) {
  try {
    return storage.getItem(key)
  } catch (error) {
    return null
  }
}

function safeSet(storage, key, value) {
  try {
    storage.setItem(key, value)
  } catch (error) {
    /* 隐私模式/存储已满时忽略, 不影响本次会话使用 */
  }
}

function safeRemove(storage, key) {
  try {
    storage.removeItem(key)
  } catch (error) {
    /* 忽略 */
  }
}

function readPersisted(key) {
  const sessionValue = safeGet(sessionStorage, key)
  return sessionValue !== null ? sessionValue : safeGet(localStorage, key)
}

function persist(key, value, persistent) {
  if (value === null || value === undefined || value === '') {
    safeRemove(localStorage, key)
    safeRemove(sessionStorage, key)
    return
  }
  if (persistent) {
    safeSet(localStorage, key, value)
    safeRemove(sessionStorage, key)
  } else {
    safeSet(sessionStorage, key, value)
    safeRemove(localStorage, key)
  }
}

function readUser() {
  const raw = readPersisted(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch (error) {
    return null
  }
}

export const authState = reactive({
  token: readPersisted(TOKEN_KEY) || '',
  user: readUser(),
})

export function setSession(token, user, persistent = true) {
  authState.token = token || ''
  authState.user = user || null

  persist(TOKEN_KEY, token || null, persistent)
  persist(USER_KEY, user ? JSON.stringify(user) : null, persistent)
}

export function clearSession() {
  authState.token = ''
  authState.user = null
  persist(TOKEN_KEY, null, true)
  persist(USER_KEY, null, true)
}

export function isAuthenticated() {
  return Boolean(authState.token)
}
