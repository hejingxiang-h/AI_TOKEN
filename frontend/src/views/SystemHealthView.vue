<script setup lang="ts">
import { ElButton, ElSkeleton } from 'element-plus'
import { storeToRefs } from 'pinia'
import { computed, defineAsyncComponent, onMounted } from 'vue'

import StatusPill from '../components/StatusPill.vue'
import { useHealthStore } from '../stores/health'

const LatencyChart = defineAsyncComponent(() => import('../components/LatencyChart.vue'))
const store = useHealthStore()
const { result, checkedAt, loading, error } = storeToRefs(store)

const dependencies = computed(() =>
  result.value
    ? [
        { name: 'PostgreSQL', protocol: 'SELECT 1', check: result.value.checks.postgresql },
        { name: 'Redis', protocol: 'PING', check: result.value.checks.redis },
      ]
    : [],
)
const overall = computed(() => {
  if (error.value) return { label: '请求失败', tone: 'bad' as const }
  if (!result.value) return { label: '等待检查', tone: 'neutral' as const }
  return result.value.status === 'ready'
    ? { label: '运行正常', tone: 'good' as const }
    : { label: '依赖异常', tone: 'bad' as const }
})

onMounted(() => void store.refresh())
</script>

<template>
  <section aria-labelledby="health-heading">
    <div class="page-heading">
      <div>
        <h1 id="health-heading">系统健康</h1>
        <p>查看后端服务及其 PostgreSQL、Redis 连接状态。</p>
      </div>
      <ElButton type="primary" :loading="loading" @click="store.refresh">重新检查</ElButton>
    </div>

    <div class="summary" aria-live="polite">
      <div>
        <h2>服务状态</h2>
        <p v-if="checkedAt">上次检查 {{ checkedAt.toLocaleTimeString('zh-CN') }}</p>
        <p v-else>尚无检查结果</p>
      </div>
      <StatusPill :tone="overall.tone" :label="overall.label" />
    </div>

    <p v-if="error" class="failure" role="alert">{{ error }}</p>
    <ElSkeleton v-if="loading && !result" class="loading" :rows="3" animated />

    <template v-if="result">
      <div class="dependency-grid">
        <article v-for="dependency in dependencies" :key="dependency.name" class="dependency-card">
          <div class="card-top">
            <h2>{{ dependency.name }}</h2>
            <StatusPill
              :tone="dependency.check.status === 'up' ? 'good' : 'bad'"
              :label="dependency.check.status === 'up' ? '已连接' : '连接失败'"
            />
          </div>
          <div class="card-bottom">
            <code>{{ dependency.protocol }}</code>
            <span>{{ dependency.check.latency_ms }} ms</span>
          </div>
        </article>
      </div>

      <section class="chart-card" aria-labelledby="latency-heading">
        <h2 id="latency-heading">本次连接耗时</h2>
        <LatencyChart :checks="result.checks" />
      </section>
    </template>
  </section>
</template>
