/**
 * 全局登录状态(响应式)
 *
 * 通过 localStorage 持久化, 并提供响应式状态供组件使用。
 */
import { reactive } from 'vue'

const TOKEN_KEY = 'access_token'
const USER_KEY = 'user_info'

function readUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch (error) {
    return null
  }
}

export const authState = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: readUser(),
})

export function setSession(token, user) {
  authState.token = token || ''
  authState.user = user || null

  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }

  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(USER_KEY)
  }
}

export function clearSession() {
  setSession('', null)
}

export function isAuthenticated() {
  return Boolean(authState.token)
}