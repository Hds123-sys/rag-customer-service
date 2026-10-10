import axios from 'axios'
import { authState, clearSession } from '../store/auth'

const api = axios.create({
  baseURL: '/api',
  // 大模型生成答案可能耗时较久, 超时设置得宽松一些
  timeout: 180000,
})

// 请求拦截器: 自动携带 Token
api.interceptors.request.use(
  (config) => {
    if (authState.token) {
      config.headers.Authorization = `Bearer ${authState.token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器: 统一处理 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearSession()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

/**
 * 从 axios 错误对象中提取可读的错误信息
 */
export function extractErrorMessage(error, fallback = '请求失败, 请稍后重试') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail) {
    return detail
  }
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item?.msg || '').filter(Boolean).join('; ') || fallback
  }
  if (error?.code === 'ECONNABORTED') {
    return '请求超时, 请稍后重试'
  }
  return error?.message || fallback
}

export const documentAPI = {
  upload: (file, onUploadProgress) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress,
    })
  },
  list: () => api.get('/documents'),
  remove: (id) => api.delete(`/documents/${encodeURIComponent(id)}`),
  clear: () => api.post('/documents/clear'),
  stats: () => api.get('/documents/stats'),
}

export const chatAPI = {
  send: (message, sessionId, history = []) =>
    api.post('/chat', { message, session_id: sessionId, chat_history: history }),
  getHistory: (sessionId) => api.get(`/chat/history/${encodeURIComponent(sessionId)}`),
  clearHistory: (sessionId) => api.delete(`/chat/history/${encodeURIComponent(sessionId)}`),
  clearAllHistory: () => api.delete('/chat/history'),
}

export default api