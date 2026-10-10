<template>
  <div class="auth-container">
    <div class="auth-card">
      <div class="auth-header">
        <el-icon class="auth-icon" size="46" color="#667eea"><UserFilled /></el-icon>
        <h2>注册新账号</h2>
        <p class="auth-subtitle">注册后即可上传文档并进行智能问答</p>
      </div>

      <el-form
        ref="registerForm"
        :model="registerData"
        :rules="registerRules"
        class="auth-form"
        @submit.prevent="handleRegister"
      >
        <el-form-item prop="username">
          <el-input v-model="registerData.username" placeholder="用户名(3-50位字母/数字/下划线)" size="large" clearable>
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-form-item prop="email">
          <el-input v-model="registerData.email" placeholder="邮箱" size="large" clearable>
            <template #prefix><el-icon><Message /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="registerData.password"
            type="password"
            placeholder="密码(至少6位)"
            size="large"
            show-password
            @input="checkPasswordStrength"
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
          <div v-if="registerData.password" class="password-strength">
            <div class="strength-bar">
              <div class="strength-fill" :class="passwordStrengthClass" :style="{ width: `${passwordStrength}%` }" />
            </div>
            <span class="strength-text" :class="passwordStrengthClass">强度: {{ passwordStrengthText }}</span>
          </div>
        </el-form-item>

        <el-form-item prop="confirmPassword">
          <el-input
            v-model="registerData.confirmPassword"
            type="password"
            placeholder="确认密码"
            size="large"
            show-password
            @keyup.enter="handleRegister"
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-form-item>
          <div class="terms">
            <el-checkbox v-model="agreeTerms">我已阅读并同意</el-checkbox>
            <el-link type="primary" underline="never" @click="openAgreement('terms')">用户协议</el-link>
            <span>和</span>
            <el-link type="primary" underline="never" @click="openAgreement('privacy')">隐私政策</el-link>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="auth-button"
            :loading="loading"
            :disabled="!agreeTerms"
            @click="handleRegister"
          >
            注册
          </el-button>
        </el-form-item>
      </el-form>

      <div class="auth-footer">
        <span>已有账号？</span>
        <el-link type="primary" @click="$router.push('/login')">立即登录</el-link>
      </div>
    </div>

    <el-dialog v-model="agreementVisible" :title="agreementTitle" width="560px">
      <div class="agreement-body">
        <p v-for="(paragraph, index) in agreementParagraphs" :key="index">{{ paragraph }}</p>
      </div>
      <template #footer>
        <el-button type="primary" @click="agreementVisible = false">我知道了</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, Message, User, UserFilled } from '@element-plus/icons-vue'
import auth from '../services/auth'
import { extractErrorMessage } from '../services/api'

const router = useRouter()
const loading = ref(false)
const agreeTerms = ref(false)
const passwordStrength = ref(0)

const registerForm = ref(null)
const registerData = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const checkPasswordStrength = () => {
  const password = registerData.password
  let strength = 0
  if (password.length >= 8) strength += 25
  if (password.length >= 12) strength += 15
  if (/[a-z]/.test(password)) strength += 15
  if (/[A-Z]/.test(password)) strength += 15
  if (/[0-9]/.test(password)) strength += 15
  if (/[^a-zA-Z0-9]/.test(password)) strength += 15
  passwordStrength.value = Math.min(100, strength)
}

const passwordStrengthClass = computed(() => {
  if (passwordStrength.value < 30) return 'weak'
  if (passwordStrength.value < 60) return 'medium'
  return 'strong'
})

const passwordStrengthText = computed(() => {
  if (passwordStrength.value < 30) return '弱'
  if (passwordStrength.value < 60) return '中'
  return '强'
})

const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度为3-50个字符', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '用户名只能包含字母、数字和下划线', trigger: 'blur' },
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' },
  ],
  confirmPassword: [
    {
      validator: (_rule, value, callback) => {
        if (!value) callback(new Error('请再次输入密码'))
        else if (value !== registerData.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

const agreementVisible = ref(false)
const agreementType = ref('terms')

const AGREEMENTS = {
  terms: {
    title: '用户协议',
    paragraphs: [
      '欢迎使用智能客服RAG系统(以下简称「本系统」)。在使用本系统前, 请您仔细阅读并充分理解本协议。',
      '一、服务内容: 本系统提供文档上传、知识库管理与基于知识库的智能问答服务。',
      '二、账号安全: 请您妥善保管账号与密码, 因账号泄露造成的损失由您自行承担。',
      '三、使用规范: 您不得上传违法违规、侵犯他人合法权益的内容, 不得利用本系统从事任何违法活动。',
      '四、内容归属: 您上传的文档归您所有, 本系统仅用于为您提供问答服务, 不作其他用途。',
      '五、服务变更: 本系统可能因升级、维护等原因调整或暂停服务, 我们会尽量提前告知。',
    ],
  },
  privacy: {
    title: '隐私政策',
    paragraphs: [
      '我们非常重视您的个人信息保护。本政策说明我们如何收集、使用与保护您的信息。',
      '一、收集范围: 我们仅收集注册所需的用户名、邮箱, 以及您主动上传的文档内容。',
      '二、使用目的: 上述信息仅用于账号登录、知识库检索与智能问答, 不作其他用途。',
      '三、存储方式: 您的密码经加密后存储, 我们不会以明文形式保存或展示您的密码。',
      '四、数据隔离: 您上传的文档与对话记录仅您本人可见, 其他用户无法检索到您的资料。',
      '五、信息共享: 除法律法规要求外, 我们不会向任何第三方出售或提供您的个人信息。',
      '六、您的权利: 您可以随时删除已上传的文档、清空对话记录, 或申请注销账号。',
    ],
  },
}

const agreementTitle = computed(() => AGREEMENTS[agreementType.value].title)
const agreementParagraphs = computed(() => AGREEMENTS[agreementType.value].paragraphs)

const openAgreement = (type) => {
  agreementType.value = type
  agreementVisible.value = true
}

const handleRegister = async () => {
  if (!agreeTerms.value) {
    ElMessage.warning('请先同意用户协议和隐私政策')
    return
  }
  if (!registerForm.value) return

  try {
    await registerForm.value.validate()
  } catch (error) {
    return
  }

  loading.value = true
  try {
    const response = await auth.register({
      username: registerData.username,
      email: registerData.email,
      password: registerData.password,
    })
    auth.setToken(response.access_token)
    auth.setUserInfo(response.user)
    ElMessage.success('注册成功, 欢迎使用！')
    router.push('/')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '注册失败, 请稍后重试'))
  } finally {
    loading.value = false
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
  max-width: 440px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.auth-header {
  text-align: center;
  margin-bottom: 24px;
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

.password-strength {
  margin-top: 8px;
  width: 100%;
}

.strength-bar {
  height: 4px;
  background: #e0e0e0;
  border-radius: 2px;
  overflow: hidden;
}

.strength-fill {
  height: 100%;
  transition: width 0.3s ease;
}

.strength-fill.weak {
  background: #f56c6c;
}

.strength-fill.medium {
  background: #e6a23c;
}

.strength-fill.strong {
  background: #67c23a;
}

.strength-text {
  font-size: 12px;
  margin-left: 4px;
}

.strength-text.weak {
  color: #f56c6c;
}

.strength-text.medium {
  color: #e6a23c;
}

.strength-text.strong {
  color: #67c23a;
}

.terms {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  color: #606266;
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
.agreement-body p {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.8;
  color: #606266;
}
</style>