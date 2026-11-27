<script setup lang="ts">
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { type EChartsType, init, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { HealthResponse } from '../types/health'

const props = defineProps<{ checks: HealthResponse['checks'] }>()
const canvas = ref<HTMLDivElement>()
let chart: EChartsType | undefined
let observer: ResizeObserver | undefined

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

function draw(): void {
  chart?.setOption({
    animation: false,
    tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => String(value) + ' ms' },
    grid: { left: 93, right: 32, top: 12, bottom: 26 },
    xAxis: {
      type: 'value',
      axisLabel: { formatter: '{value} ms', color: '#5b6a80' },
      splitLine: { lineStyle: { color: '#edf1f7' } },
    },
    yAxis: {
      type: 'category',
      data: ['Redis', 'PostgreSQL'],
      axisLabel: { color: '#475973' },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        barWidth: 16,
        data: [props.checks.redis, props.checks.postgresql].map((check) => ({
          value: check.latency_ms,
          itemStyle: { color: check.status === 'up' ? '#4f6cea' : '#c55349', borderRadius: 4 },
        })),
      },
    ],
  })
}

onMounted(() => {
  if (!canvas.value) return
  chart = init(canvas.value)
  draw()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(canvas.value)
})

watch(() => props.checks, draw)
onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div
    ref="canvas"
    class="latency-chart"
    role="img"
    :aria-label="
      '连接耗时，PostgreSQL ' +
      checks.postgresql.latency_ms +
      ' 毫秒，Redis ' +
      checks.redis.latency_ms +
      ' 毫秒'
    "
  ></div>
</template>
