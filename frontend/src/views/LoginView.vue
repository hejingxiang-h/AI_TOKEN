<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
const user = ref(''),
  password = ref(''),
  error = ref('')
const router = useRouter(),
  route = useRoute()
async function login() {
  if (!user.value.trim() || password.value.length < 6) {
    error.value = '请输入演示用户名和至少 6 位演示口令。'
    return
  }
  try {
    sessionStorage.setItem('gateway-demo-session', user.value.trim())
  } catch {
    error.value = '无法使用浏览器会话存储。'
    return
  }
  const next =
    typeof route.query.next === 'string' && /^\/(?!\/)/.test(route.query.next)
      ? route.query.next
      : '/'
  await router.replace(next)
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
      <form class="card login-card" novalidate @submit.prevent="login">
        <span class="demo-label">模拟环境</span>
        <h2>登录管理后台</h2>
        <p>使用任意演示用户名和至少 6 位演示口令。请勿填写真实凭据。</p>
        <label>用户名<input v-model="user" autocomplete="off" placeholder="输入演示用户名" /></label
        ><label
          >演示口令<input
            v-model="password"
            type="password"
            autocomplete="off"
            placeholder="至少 6 位" /></label
        ><small v-if="error" role="alert">{{ error }}</small
        ><button class="primary">登录演示工作区</button>
      </form>
    </section>
  </main>
</template>
