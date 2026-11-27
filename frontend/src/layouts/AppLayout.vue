<script setup lang="ts">
import { useAuth } from '../stores/auth'
import FormDialog from '../components/FormDialog.vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { sections as mockSections } from '../mock/catalog'
import { management } from '../api/management'
const sections = [...management, ...mockSections]
const router = useRouter()
const collapsed = ref(false)
const groups = [...new Set(sections.map((x) => x.group))]
const glyphs: Record<string, string> = {
  Users: '♙',
  OfficeBuilding: '▥',
  Folder: '▱',
  Key: '⚿',
  Coin: '◉',
  Cpu: '▣',
  Tickets: '≡',
  Document: '▤',
  Bell: '◇',
  Lock: '♧',
  Setting: '⚙',
}
const auth = useAuth()
const authError = ref('')
const passwordOpen = ref(false)
const current = ref('')
const replacement = ref('')
function openPassword() {
  authError.value = ''
  passwordOpen.value = true
}
async function logout() {
  try {
    await auth.logout()
    await router.push('/login')
  } catch {
    authError.value = '退出失败，请检查服务后重试。'
  }
}
async function changePassword() {
  authError.value = ''
  if (!current.value || replacement.value.length < 12) {
    authError.value = '请输入当前密码和至少 12 位的新密码。'
    return
  }
  try {
    await auth.changePassword(current.value, replacement.value)
    passwordOpen.value = false
    await router.push('/login')
  } catch {
    authError.value = '修改密码失败，请检查当前密码或重新登录。'
  } finally {
    current.value = ''
    replacement.value = ''
  }
}
</script>
<template>
  <div class="shell" :class="{ collapsed }">
    <aside class="side">
      <RouterLink to="/" class="brand-line" title="AI Token Gateway"
        ><span class="brand-mark">TG</span><strong>AI Token Gateway</strong></RouterLink
      >
      <nav aria-label="主菜单">
        <p>概览</p>
        <RouterLink to="/dashboard" title="首页工作台" aria-label="首页工作台"
          ><i>⌂</i><span>首页工作台</span></RouterLink
        ><RouterLink to="/statistics" title="Token 统计" aria-label="Token 统计"
          ><i>▥</i><span>Token 统计</span></RouterLink
        >
        <template v-for="group in groups" :key="group"
          ><p>{{ group }}</p>
          <RouterLink
            v-for="item in sections.filter((x) => x.group === group)"
            :key="item.path"
            :to="'/' + item.path"
            :title="item.title"
            :aria-label="item.title"
            ><i>{{ glyphs[item.icon] }}</i
            ><span>{{ item.title }}</span></RouterLink
          ></template
        >
      </nav>
    </aside>
    <div class="content">
      <header class="top">
        <div class="actions">
          <button
            class="toggle"
            :aria-label="collapsed ? '展开菜单' : '折叠菜单'"
            :aria-expanded="!collapsed"
            @click="collapsed = !collapsed"
          >
            ☰</button
          ><span>管理后台</span><span class="breadcrumb">/</span
          ><strong>{{ $route.meta.title }}</strong>
        </div>
        <div class="actions">
          <span v-if="!$route.meta.live" class="demo-label">模拟数据</span
          ><span class="account">{{ auth.user?.display_name }}</span
          ><button @click="openPassword">修改密码</button><button @click="logout">退出</button>
        </div>
      </header>
      <main class="work">
        <p v-if="authError && !passwordOpen" role="alert">{{ authError }}</p>
        <RouterView :key="$route.path" />
      </main>
    </div>
  </div>
  <FormDialog v-model="passwordOpen" title="修改密码" @submit="changePassword">
    <label class="field"
      >当前密码<input v-model="current" type="password" autocomplete="current-password"
    /></label>
    <label class="field"
      >新密码<input v-model="replacement" type="password" autocomplete="new-password"
    /></label>
    <p v-if="authError" role="alert">{{ authError }}</p>
  </FormDialog>
</template>
