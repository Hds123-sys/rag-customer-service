import axios from 'axios'
import { authState, clearSession, isAuthenticated as isAuth, setSession } from '../store/auth'

const authAPI = axios.create({
  baseURL: '/api/auth',
  timeout: 30000,
})

// 请求拦截器: 添加 token
authAPI.interceptors.request.use(
  (config) => {
    if (authState.token) {
      config.headers.Authorization = `Bearer ${authState.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器: 直接返回 data, 并统一处理 401
authAPI.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      clearSession()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default {
  // 注册
  register: (data) => authAPI.post('/register', data),

  // 登录
  login: (data) => authAPI.post('/login', data),

  // 退出
  logout: () => authAPI.post('/logout'),

  // 获取当前用户信息
  getCurrentUser: () => authAPI.get('/me'),

  // 密码重置: 请求验证码
  resetPassword: (email) => authAPI.post('/reset-password', { email }),

  // 密码重置: 提交验证码与新密码
  resetPasswordConfirm: (payload) => authAPI.post('/reset-password/confirm', payload),

  // ---- 登录状态管理 ----
  setToken: (token) => setSession(token, authState.user),
  setUserInfo: (user) => setSession(authState.token, user),
  getUserInfo: () => authState.user,
  getToken: () => authState.token,
  removeToken: clearSession,
  isAuthenticated: isAuth,
}