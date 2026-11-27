<script setup lang="ts">
import { ElMenu, ElMenuItem } from 'element-plus'
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="admin">
    <aside class="sidebar" aria-label="侧栏">
      <RouterLink class="brand" to="/" aria-label="AI Token Gateway 首页">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>AI Token Gateway</span>
      </RouterLink>
      <nav class="sidebar-nav" aria-label="主导航">
        <ElMenu router :default-active="route.path">
          <ElMenuItem index="/system/health">
            <span class="menu-signal" aria-hidden="true"></span>
            系统健康
          </ElMenuItem>
        </ElMenu>
      </nav>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <span>管理后台</span>
        <a href="/docs" target="_blank" rel="noopener"
          >API 文档 <span aria-hidden="true">↗</span></a
        >
      </header>
      <main class="page">
        <RouterView />
      </main>
    </div>
  </div>
</template>
