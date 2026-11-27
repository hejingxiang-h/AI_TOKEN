<script setup lang="ts">
import { isAxiosError } from 'axios'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'

const user = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const router = useRouter()
const route = useRoute()
const auth = useAuth()

async function login(): Promise<void> {
  if (loading.value) return
  if (!user.value.trim() || !password.value) {
    error.value = '请输入用户名和密码。'
    return
  }
  error.value = ''
  loading.value = true
  try {
    await auth.login(user.value.trim(), password.value)
    const next =
      typeof route.query.next === 'string' && /^\/(?!\/)/.test(route.query.next)
        ? route.query.next
        : '/'
    await router.replace(next)
  } catch (cause) {
    error.value =
      isAxiosError(cause) && cause.response?.status === 401
        ? '用户名、密码或账号状态无效。'
        : '无法登录，请检查服务配置和网络后重试。'
  } finally {
    password.value = ''
    loading.value = false
  }
}
</script>

<template>
  <main class="login">
    <section class="login-brand">
      <span class="brand-mark">TG</span>
      <h1>AI Token Gateway</h1>
      <p>企业 AI 用量与模型治理工作台</p>
    </section>
    <section class="login-content">
      <form class="card login-card" @submit.prevent="login">
        <h2>登录管理后台</h2>
        <label>用户名<input v-model="user" autocomplete="username" maxlength="254" /></label>
        <label
          >密码<input
            v-model="password"
            type="password"
            autocomplete="current-password"
            maxlength="256"
        /></label>
        <small v-if="error" role="alert">{{ error }}</small>
        <button class="primary" :disabled="loading">{{ loading ? '正在登录…' : '登录' }}</button>
      </form>
    </section>
  </main>
</template>
