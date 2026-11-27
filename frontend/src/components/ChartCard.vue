<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { init, use, type EChartsType, type EChartsCoreOption } from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
use([
  LineChart,
  BarChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
])
const props = defineProps<{ title: string; option: EChartsCoreOption }>()
const host = ref<HTMLDivElement>()
let chart: EChartsType | undefined
let resize: ResizeObserver | undefined
onMounted(() => {
  if (!host.value) return
  chart = init(host.value)
  chart.setOption(props.option)
  resize = new ResizeObserver(() => chart?.resize())
  resize.observe(host.value)
})
watch(
  () => props.option,
  (next) => chart?.setOption(next, true),
)
onBeforeUnmount(() => {
  resize?.disconnect()
  chart?.dispose()
})
</script>
<template>
  <article class="card chart-card">
    <h2>{{ title }}</h2>
    <div ref="host" class="chart" role="img" :aria-label="title" />
  </article>
</template>
