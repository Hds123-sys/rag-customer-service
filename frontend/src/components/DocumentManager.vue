<template>
  <div class="doc-page">
    <el-card shadow="never">
      <template #header>
        <div class="doc-header">
          <div class="doc-header-left">
            <h4>文档管理</h4>
            <el-tag size="small" effect="plain" type="info">共 {{ documents.length }} 个文档</el-tag>
            <el-tag v-if="stats.vector_points !== null" size="small" effect="plain" type="success">
              向量片段 {{ stats.vector_points }} ({{ stats.vector_backend || '-' }})
            </el-tag>
          </div>
          <div class="doc-header-right">
            <el-button :icon="Refresh" size="small" :loading="loading" @click="fetchDocuments">刷新</el-button>
            <el-popconfirm
              title="确定要清空所有文档吗？此操作不可恢复。"
              :disabled="documents.length === 0"
              @confirm="handleClearAll"
            >
              <template #reference>
                <el-button type="danger" plain size="small" :icon="Delete" :disabled="documents.length === 0">
                  清空全部
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </template>

      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        multiple
        :auto-upload="false"
        :show-file-list="false"
        accept=".pdf,.txt,.md"
        :disabled="uploading"
        :on-change="handleUpload"
      >
        <el-icon class="el-icon--upload" size="46" color="#667eea"><UploadFilled /></el-icon>
        <div class="upload-text">{{ uploading ? '上传中...' : '点击或拖拽文件到此区域上传' }}</div>
        <div class="upload-hint">支持 PDF、TXT、MD 格式, 单个文件最大 10MB</div>
      </el-upload>

      <div v-if="queue.length" class="upload-queue">
        <div v-for="item in queue" :key="item.uid" class="queue-item">
          <el-icon v-if="item.status === 'success'" color="#67c23a"><CircleCheck /></el-icon>
          <el-icon v-else-if="item.status === 'error'" color="#f56c6c"><CircleClose /></el-icon>
          <el-icon v-else class="is-loading"><Loading /></el-icon>
          <span class="queue-name">{{ item.name }}</span>
          <span v-if="item.status === 'error'" class="queue-error">{{ item.error }}</span>
          <el-button v-else-if="item.status === 'uploading'" text size="small">处理中 {{ item.percent }}%</el-button>
          <el-button v-else text size="small" type="success">已完成</el-button>
        </div>
        <div class="queue-actions">
          <el-button text size="small" @click="queue = []">清除记录</el-button>
        </div>
      </div>

      <el-table :data="documents" v-loading="loading" style="width: 100%" empty-text="暂无文档, 请上传文档">
        <el-table-column prop="filename" label="文件名" min-width="220">
          <template #default="{ row }">
            <el-space>
              <el-icon><Document /></el-icon>
              <span class="file-name">{{ row.filename }}</span>
            </el-space>
          </template>
        </el-table-column>
        <el-table-column prop="file_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ (row.file_type || '-').toUpperCase() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="size" label="大小" width="110">
          <template #default="{ row }">{{ formatFileSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="chunks" label="片段数" width="90" />
        <el-table-column prop="created_at" label="上传时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'processed' ? 'success' : 'warning'">
              {{ row.status === 'processed' ? '已处理' : row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-popconfirm title="确定要删除这个文档吗？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button type="danger" link :icon="Delete">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  CircleClose,
  Delete,
  Document,
  Loading,
  Refresh,
  UploadFilled,
} from '@element-plus/icons-vue'
import { documentAPI, extractErrorMessage } from '../services/api'
import { authState } from '../store/auth'

const documents = ref([])
const loading = ref(false)
const uploading = ref(false)
const uploadRef = ref(null)
const queue = ref([])
const stats = reactive({ vector_points: null, vector_backend: '' })

onMounted(() => {
  fetchDocuments()
  fetchStats()
})

async function fetchDocuments() {
  if (!authState.token) return
  loading.value = true
  try {
    const { data } = await documentAPI.list()
    documents.value = Array.isArray(data) ? data : []
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '获取文档列表失败'))
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  if (!authState.token) return
  try {
    const { data } = await documentAPI.stats()
    stats.vector_points = data.vector_points ?? 0
    stats.vector_backend = data.vector_backend || ''
  } catch (error) {
    stats.vector_points = null
    stats.vector_backend = ''
  }
}

async function handleUpload(uploadFile) {
  const raw = uploadFile?.raw
  if (!raw) return

  const extension = `.${raw.name.split('.').pop()?.toLowerCase() || ''}`
  if (!['.pdf', '.txt', '.md'].includes(extension)) {
    queue.value.push({ uid: uploadFile.uid, name: raw.name, status: 'error', percent: 0, error: `不支持的类型: ${extension}` })
    uploadRef.value?.clearFiles()
    return
  }

  const item = reactive({ uid: uploadFile.uid, name: raw.name, status: 'uploading', percent: 0, error: '' })
  queue.value.push(item)
  uploading.value = true

  try {
    await documentAPI.upload(raw, (event) => {
      if (event.total) {
        item.percent = Math.min(99, Math.round((event.loaded / event.total) * 100))
      }
    })
    item.status = 'success'
    item.percent = 100
    await Promise.all([fetchDocuments(), fetchStats()])
  } catch (error) {
    item.status = 'error'
    item.error = extractErrorMessage(error, '上传失败')
  } finally {
    uploading.value = false
    uploadRef.value?.clearFiles()
  }
}

async function handleDelete(id) {
  try {
    await documentAPI.remove(id)
    ElMessage.success('文档删除成功')
    await Promise.all([fetchDocuments(), fetchStats()])
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '文档删除失败'))
  }
}

async function handleClearAll() {
  try {
    await documentAPI.clear()
    ElMessage.success('所有文档已清空')
    queue.value = []
    await Promise.all([fetchDocuments(), fetchStats()])
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '清空失败'))
  }
}

function formatFileSize(bytes) {
  const value = Number(bytes) || 0
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(2)} KB`
  return `${(value / (1024 * 1024)).toFixed(2)} MB`
}

function formatDate(timestamp) {
  if (!timestamp) return '-'
  return new Date(Number(timestamp) * 1000).toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.doc-page {
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
  overflow-y: auto;
}

.doc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.doc-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.doc-header-left h4 {
  margin: 0;
  font-size: 16px;
}

.doc-header-right {
  display: flex;
  gap: 8px;
}

.upload-area {
  margin-bottom: 16px;
}

.upload-text {
  font-size: 15px;
  margin: 8px 0;
  color: #606266;
}

.upload-hint {
  font-size: 12px;
  color: #a8abb2;
}

.upload-queue {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 8px;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}

.queue-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-error {
  color: #f56c6c;
  font-size: 12px;
}

.queue-actions {
  text-align: right;
}

.file-name {
  word-break: break-all;
}
</style>