<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { sections } from '../mock/catalog'
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
const user = sessionStorage.getItem('gateway-demo-session')
function logout() {
  sessionStorage.removeItem('gateway-demo-session')
  void router.push('/login')
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
          <span class="demo-label">模拟数据</span><span class="account">{{ user }}</span
          ><button @click="logout">退出</button>
        </div>
      </header>
      <main class="work"><RouterView :key="$route.path" /></main>
    </div>
  </div>
</template>
