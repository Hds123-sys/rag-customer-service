<template>
  <div class="chat-page">
    <el-card class="chat-card" shadow="never">
      <template #header>
        <div class="chat-header">
          <div class="chat-header-left">
            <h4>智能问答</h4>
            <el-tag v-if="stats.documents !== null" size="small" :type="stats.documents > 0 ? 'success' : 'warning'" effect="plain">
              {{ stats.documents > 0 ? `知识库: ${stats.documents} 个文档 / ${stats.vector_points} 个片段` : '知识库为空' }}
            </el-tag>
          </div>
          <el-popconfirm
            title="确定要清空对话历史吗？"
            :disabled="messages.length === 0"
            @confirm="handleClearHistory"
          >
            <template #reference>
              <el-button type="danger" plain size="small" :icon="Delete" :disabled="messages.length === 0">
                清空对话
              </el-button>
            </template>
          </el-popconfirm>
        </div>
      </template>

      <el-alert
        v-if="stats.documents === 0"
        class="kb-alert"
        type="warning"
        :closable="false"
        show-icon
        title="知识库为空"
        description="请先前往「文档管理」上传 PDF / TXT / MD 文档, 之后即可基于文档内容进行问答。"
      />

      <div ref="messageListRef" class="message-list">
        <el-empty v-if="messages.length === 0" description="开始提问吧, 我会基于您上传的文档给出回答" />

        <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role">
          <el-avatar :size="36" :style="{ backgroundColor: msg.role === 'user' ? '#667eea' : '#52c41a' }">
            <el-icon v-if="msg.role === 'user'"><User /></el-icon>
            <el-icon v-else><Service /></el-icon>
          </el-avatar>

          <div class="message-body">
            <div class="message-meta">
              <strong class="message-role" :class="msg.role">{{ msg.role === 'user' ? '你' : 'AI助手' }}</strong>
              <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
              <el-button
                v-if="msg.role === 'assistant'"
                text
                size="small"
                :icon="DocumentCopy"
                title="复制回答"
                @click="handleCopy(msg.content)"
              />
            </div>

            <div class="message-content" :class="msg.role">{{ msg.content }}</div>

            <div v-if="msg.sources && msg.sources.length" class="message-sources">
              <span class="sources-label">参考来源:</span>
              <el-popover
                v-for="(source, index) in msg.sources"
                :key="source.id || index"
                placement="top"
                :width="380"
                trigger="hover"
              >
                <template #reference>
                  <el-tag type="primary" effect="plain" size="small" class="source-tag">
                    {{ source.filename || '文档片段' }} · 相似度 {{ (source.score * 100).toFixed(1) }}%
                  </el-tag>
                </template>
                <div class="source-popover">
                  <div class="source-popover-title">
                    {{ source.filename || '文档片段' }} (片段 #{{ (source.chunk_index || 0) + 1 }})
                  </div>
                  <div class="source-popover-text">{{ source.text }}</div>
                  <el-button text type="primary" size="small" @click="handleCopy(source.text)">复制片段</el-button>
                </div>
              </el-popover>
            </div>
          </div>
        </div>

        <div v-if="loading" class="message assistant">
          <el-avatar :size="36" style="background: #52c41a"><el-icon><Service /></el-icon></el-avatar>
          <div class="message-body">
            <div class="message-meta">
              <strong class="message-role assistant">AI助手</strong>
            </div>
            <div class="message-content assistant thinking">正在思考中...</div>
          </div>
        </div>

        <div ref="bottomRef" />
      </div>

      <div class="chat-input">
        <el-input
          v-model="inputValue"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入您的问题, Enter 发送, Shift+Enter 换行"
          :disabled="loading"
          @keydown.enter.exact.prevent="handleSend"
        />
        <el-button type="primary" :icon="Promotion" :loading="loading" @click="handleSend">发送</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, DocumentCopy, Promotion, Service, User } from '@element-plus/icons-vue'
import { chatAPI, documentAPI, extractErrorMessage } from '../services/api'
import { authState } from '../store/auth'

const SESSION_KEY = 'rag_chat_session_id'

function resolveSessionId() {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

const sessionId = ref(resolveSessionId())
const messages = ref([])
const inputValue = ref('')
const loading = ref(false)
const stats = reactive({ documents: null, vector_points: 0 })
const messageListRef = ref(null)
const bottomRef = ref(null)

let messageSeq = 0
function buildMessage(role, content, extra = {}, timestamp) {
  messageSeq += 1
  return { id: `${Date.now()}_${messageSeq}`, role, content, timestamp: timestamp ?? Date.now(), ...extra }
}

function scrollToBottom() {
  nextTick(() => {
    bottomRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  })
}

watch(messages, scrollToBottom, { deep: true })

async function loadStats() {
  if (!authState.token) return
  try {
    const { data } = await documentAPI.stats()
    stats.documents = data.documents ?? 0
    stats.vector_points = data.vector_points ?? 0
  } catch (error) {
    // 统计失败时保持未知状态, 不误报"知识库为空"
    stats.documents = null
  }
}

onMounted(async () => {
  await Promise.all([loadStats(), restoreHistory()])
})

// 刷新页面后从服务端恢复本轮会话历史, 避免"对话凭空消失"
async function restoreHistory() {
  if (!authState.token) return
  try {
    const { data } = await chatAPI.getHistory(sessionId.value)
    const history = Array.isArray(data?.history) ? data.history : []
    if (!history.length) return
    messages.value = history
      .filter((item) => item && typeof item.content === 'string' && item.content)
      .map((item) =>
        buildMessage(
          item.role === 'user' ? 'user' : 'assistant',
          item.content,
          { sources: Array.isArray(item.sources) ? item.sources : [] },
          item.ts ? item.ts * 1000 : undefined,
        )
      )
  } catch (error) {
    // 历史恢复失败不影响新的提问
  }
}

async function handleSend() {
  if (loading.value) return
  if (!authState.token) {
    ElMessage.warning('请先登录')
    return
  }

  const text = inputValue.value.trim()
  if (!text) {
    ElMessage.warning('请输入消息')
    return
  }

  messages.value.push(buildMessage('user', text))
  inputValue.value = ''
  loading.value = true

  const history = messages.value.slice(0, -1).map(({ role, content }) => ({ role, content }))

  try {
    const { data } = await chatAPI.send(text, sessionId.value, history)
    if (data.session_id && data.session_id !== sessionId.value) {
      sessionId.value = data.session_id
      localStorage.setItem(SESSION_KEY, data.session_id)
    }
    messages.value.push(buildMessage('assistant', data.answer, { sources: data.sources || [] }))
    loadStats()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '发送失败, 请稍后重试'))
    messages.value.pop()
    inputValue.value = text
  } finally {
    loading.value = false
  }
}

async function handleClearHistory() {
  try {
    await chatAPI.clearHistory(sessionId.value)
  } catch (error) {
    // 服务端清空失败也不影响本地清空
  }
  messages.value = []
  ElMessage.success('对话历史已清空')
}

async function handleCopy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (error) {
    ElMessage.warning('复制失败, 请手动选择复制')
  }
}

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.chat-page {
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
}

.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: none;
}

.chat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chat-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chat-header-left h4 {
  margin: 0;
  font-size: 16px;
}

.kb-alert {
  margin-bottom: 12px;
}

.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
}

.message {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
}

.message-body {
  flex: 1;
  min-width: 0;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.message-role.user {
  color: #667eea;
}

.message-role.assistant {
  color: #52c41a;
}

.message-time {
  font-size: 12px;
  color: #a8abb2;
}

.message-content {
  padding: 12px 16px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}

.message-content.user {
  background: #f0f5ff;
}

.message-content.assistant {
  background: #f6ffed;
}

.message-content.thinking {
  color: #909399;
  font-style: italic;
}

.message-sources {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.sources-label {
  font-size: 12px;
  color: #909399;
}

.source-tag {
  cursor: pointer;
}

.source-popover-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.source-popover-text {
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 8px;
}

.chat-input {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  border-top: 1px solid #f0f0f0;
  padding-top: 16px;
}
</style>