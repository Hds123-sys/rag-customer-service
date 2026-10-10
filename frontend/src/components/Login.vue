<template>
  <div class="auth-container">
    <div class="auth-card">
      <div class="auth-header">
        <el-icon class="auth-icon" size="46" color="#667eea"><Service /></el-icon>
        <h2>智能客服RAG系统</h2>
        <p class="auth-subtitle">登录后即可使用知识库问答</p>
      </div>

      <el-form
        ref="loginForm"
        :model="loginData"
        :rules="loginRules"
        class="auth-form"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input v-model="loginData.username" placeholder="用户名或邮箱" size="large" clearable>
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginData.password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-form-item>
          <div class="form-footer">
            <el-checkbox v-model="rememberMe">记住我</el-checkbox>
            <el-link type="primary" @click="openForgotPassword">忘记密码？</el-link>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" class="auth-button" :loading="loading" @click="handleLogin">
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="auth-footer">
        <span>还没有账号？</span>
        <el-link type="primary" @click="$router.push('/register')">立即注册</el-link>
      </div>
    </div>

    <!-- 忘记密码对话框 -->
    <el-dialog v-model="showForgot" title="找回密码" width="420px" @closed="resetForgot">
      <el-steps :active="forgotStep" simple style="margin-bottom: 20px">
        <el-step title="验证邮箱" />
        <el-step title="重置密码" />
      </el-steps>

      <el-form v-if="forgotStep === 0" ref="forgotForm" :model="forgotData" :rules="forgotRules">
        <el-form-item prop="email">
          <el-input v-model="forgotData.email" placeholder="请输入注册邮箱" clearable>
            <template #prefix><el-icon><Message /></el-icon></template>
          </el-input>
        </el-form-item>
      </el-form>

      <el-form v-else ref="resetForm" :model="resetData" :rules="resetRules" label-width="0">
        <el-alert
          v-if="devCode"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
          :title="`开发模式验证码: ${devCode}`"
        />
        <el-form-item prop="code">
          <el-input v-model="resetData.code" placeholder="6位验证码" maxlength="6" clearable />
        </el-form-item>
        <el-form-item prop="newPassword">
          <el-input v-model="resetData.newPassword" type="password" placeholder="新密码(至少6位)" show-password />
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <el-input v-model="resetData.confirmPassword" type="password" placeholder="确认新密码" show-password />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showForgot = false">取消</el-button>
        <el-button v-if="forgotStep === 0" type="primary" :loading="forgotLoading" @click="handleSendCode">
          发送验证码
        </el-button>
        <el-button v-else type="primary" :loading="forgotLoading" @click="handleResetPassword">
          确认重置
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, Message, Service, User } from '@element-plus/icons-vue'
import auth from '../services/auth'
import { extractErrorMessage } from '../services/api'

const router = useRouter()
const loading = ref(false)
const rememberMe = ref(true)

const loginForm = ref(null)
const loginData = reactive({ username: '', password: '' })
const loginRules = {
  username: [{ required: true, message: '请输入用户名或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const handleLogin = async () => {
  if (!loginForm.value) return
  try {
    await loginForm.value.validate()
  } catch (error) {
    return
  }

  loading.value = true
  try {
    const response = await auth.login({ ...loginData })
    auth.setToken(response.access_token)
    auth.setUserInfo(response.user)
    ElMessage.success('登录成功')
    const redirect = router.currentRoute.value.query?.redirect
    router.push(typeof redirect === 'string' && redirect ? redirect : '/')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '登录失败, 请检查用户名和密码'))
  } finally {
    loading.value = false
  }
}

// ---------------- 忘记密码 ----------------
const showForgot = ref(false)
const forgotStep = ref(0)
const forgotLoading = ref(false)
const devCode = ref('')

const forgotForm = ref(null)
const resetForm = ref(null)

const forgotData = reactive({ email: '' })
const resetData = reactive({ code: '', newPassword: '', confirmPassword: '' })

const forgotRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
}

const resetRules = {
  code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    { len: 6, message: '验证码为6位数字', trigger: 'blur' },
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' },
  ],
  confirmPassword: [
    {
      validator: (_rule, value, callback) => {
        if (!value) callback(new Error('请再次输入新密码'))
        else if (value !== resetData.newPassword) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

const openForgotPassword = () => {
  forgotData.email = loginData.username.includes('@') ? loginData.username : ''
  showForgot.value = true
}

const resetForgot = () => {
  forgotStep.value = 0
  devCode.value = ''
  resetData.code = ''
  resetData.newPassword = ''
  resetData.confirmPassword = ''
}

const handleSendCode = async () => {
  if (!forgotForm.value) return
  try {
    await forgotForm.value.validate()
  } catch (error) {
    return
  }

  forgotLoading.value = true
  try {
    const response = await auth.resetPassword(forgotData.email)
    devCode.value = response.dev_code || ''
    ElMessage.success(response.message || '验证码已发送')
    forgotStep.value = 1
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '验证码发送失败'))
  } finally {
    forgotLoading.value = false
  }
}

const handleResetPassword = async () => {
  if (!resetForm.value) return
  try {
    await resetForm.value.validate()
  } catch (error) {
    return
  }

  forgotLoading.value = true
  try {
    await auth.resetPasswordConfirm({
      email: forgotData.email,
      code: resetData.code,
      new_password: resetData.newPassword,
    })
    ElMessage.success('密码重置成功, 请使用新密码登录')
    loginData.username = forgotData.email
    loginData.password = ''
    showForgot.value = false
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '密码重置失败'))
  } finally {
    forgotLoading.value = false
  }
}
</script>

<style scoped>
.auth-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.auth-card {
  background: #ffffff;
  border-radius: 16px;
  padding: 40px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.auth-header {
  text-align: center;
  margin-bottom: 24px;
}

.auth-icon {
  margin-bottom: 8px;
}

.auth-header h2 {
  margin: 0;
  color: #333333;
  font-weight: 600;
  font-size: 20px;
}

.auth-subtitle {
  margin: 8px 0 0;
  color: #909399;
  font-size: 13px;
}

.auth-form {
  margin-top: 12px;
}

.form-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.auth-button {
  width: 100%;
  height: 44px;
  font-size: 16px;
  border-radius: 8px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
}

.auth-footer {
  text-align: center;
  margin-top: 16px;
  color: #666666;
}

.auth-footer .el-link {
  margin-left: 5px;
}
</style>