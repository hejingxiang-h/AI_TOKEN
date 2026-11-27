<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import DataTable from '../components/DataTable.vue'
import EmptyState from '../components/EmptyState.vue'
import FormDialog from '../components/FormDialog.vue'
import { activity, bounds, dateValue, money, number, recent } from '../mock/analytics'
import { sections, type Row } from '../mock/catalog'
defineProps<{ statistics?: boolean }>()
const ChartCard = defineAsyncComponent(() => import('../components/ChartCard.vue'))
const ranges = ['今天', '昨天', '最近7天', '最近30天', '本月', '自定义']
const preset = ref('最近7天'),
  from = ref(dateValue(new Date())),
  to = ref(from.value),
  start = ref(from.value),
  end = ref(to.value),
  error = ref('')
const open = ref(false),
  detail = ref<Row>(),
  fields = sections.find((s) => s.path === 'calls')!.fields
const dates = computed(() => bounds(preset.value, start.value, end.value))
const rows = computed(() =>
  activity.filter((a) => {
    const d = dateValue(a.date)
    return d >= dates.value[0]! && d <= dates.value[1]!
  }),
)
const matches = computed(() =>
  recent
    .filter((_, i) => {
      const d = dateValue(activity[i]!.date)
      return d >= dates.value[0]! && d <= dates.value[1]!
    })
    .slice(0, 6),
)
function apply() {
  if (!from.value || !to.value || from.value > to.value) {
    error.value = '请选择有效的开始和结束日期'
    return
  }
  start.value = from.value
  end.value = to.value
  error.value = ''
}
const stats = computed(() => {
  const r = rows.value,
    input = r.reduce((s, a) => s + a.input, 0),
    output = r.reduce((s, a) => s + a.output, 0)
  return [
    ['Token 总量', number.format(input + output), '输入与输出合计', 'T'],
    ['消费金额', money.format(r.reduce((s, a) => s + a.cents, 0) / 100), '原币 USD', '$'],
    ['调用次数', number.format(r.length), '所选期间请求', '↗'],
    ['活跃用户', number.format(new Set(r.map((a) => a.user)).size), '去重用户', 'U'],
    ['输入 Token', number.format(input), '模型输入', '↓'],
    ['输出 Token', number.format(output), '模型输出', '↑'],
    ['活跃 Key', number.format(new Set(r.map((a) => a.key)).size), '去重 Key', 'K'],
    ['异常调用', number.format(r.filter((a) => a.failed).length), '模拟请求失败', '!'],
  ]
})
const daily = computed(() => {
  const data = new Map<string, { token: number; cost: number }>()
  for (const a of [...rows.value].reverse()) {
    const key = dateValue(a.date).slice(5),
      old = data.get(key) ?? { token: 0, cost: 0 }
    data.set(key, { token: old.token + a.input + a.output, cost: old.cost + a.cents })
  }
  return [...data]
})
function trend(metric: 'token' | 'cost'): EChartsCoreOption {
  const color = metric === 'token' ? '#2862e9' : '#139da3'
  return {
    color: [color],
    tooltip: { trigger: 'axis' },
    grid: { left: 52, right: 23, top: 19, bottom: 30 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: daily.value.map(([d]) => d),
      axisLine: { lineStyle: { color: '#e3eaf5' } },
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf1f7' } } },
    series: [
      {
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.11 },
        data: daily.value.map(([, v]) => (metric === 'cost' ? v.cost / 100 : v.token)),
      },
    ],
  }
}
function rank(dimension: 'department' | 'project' | 'model'): EChartsCoreOption {
  const counts = new Map<string, number>()
  for (const a of rows.value)
    counts.set(a[dimension], (counts.get(a[dimension]) ?? 0) + a.input + a.output)
  const data = [...counts].sort((a, b) => a[1] - b[1])
  if (dimension === 'model')
    return {
      color: ['#2862e9', '#5da6fa', '#42c6be'],
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['50%', '43%'],
          label: { show: false },
          data: data.map(([name, value]) => ({ name, value })),
        },
      ],
    }
  return {
    color: ['#4480f1'],
    tooltip: { trigger: 'axis' },
    grid: { left: 105, right: 24, top: 10, bottom: 28 },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf1f7' } } },
    yAxis: { type: 'category', data: data.map((a) => a[0]) },
    series: [
      { type: 'bar', barMaxWidth: 16, data: data.map((a) => a[1]), itemStyle: { borderRadius: 5 } },
    ],
  }
}
</script>
<template>
  <PageHeader
    :title="statistics ? 'Token 统计' : '首页工作台'"
    :description="
      statistics
        ? '按时间查看模拟用量、费用及模型分布。'
        : '查看企业模型调用、Token 用量和费用的模拟概览。'
    "
    ><RouterLink v-if="!statistics" class="button" to="/statistics"
      >查看 Token 统计 →</RouterLink
    ></PageHeader
  >
  <section class="card time-filter">
    <div class="actions">
      <button
        v-for="r in ranges"
        :key="r"
        :aria-pressed="preset === r"
        :class="{ chosen: preset === r }"
        @click="
          () => {
            preset = r
            error = ''
          }
        "
      >
        {{ r }}
      </button>
    </div>
    <span>{{ dates.join(' 至 ') }}</span>
    <form v-if="preset === '自定义'" class="custom-range" @submit.prevent="apply">
      <label>开始日期 <input v-model="from" type="date" /></label
      ><label>结束日期 <input v-model="to" type="date" /></label
      ><button class="primary">应用</button><small v-if="error" role="alert">{{ error }}</small>
    </form>
  </section>
  <section class="metrics">
    <StatCard
      v-for="[label, value, note, icon] in stats"
      :key="label"
      :label="label!"
      :value="value!"
      :note="note!"
      :icon="icon!"
    />
  </section>
  <EmptyState v-if="!rows.length" title="这个时段暂无模拟记录" description="请选择其他日期范围。" />
  <template v-else
    ><section class="trends">
      <ChartCard title="Token 趋势" :option="trend('token')" /><ChartCard
        title="费用趋势 · USD"
        :option="trend('cost')"
      />
    </section>
    <section class="rankings">
      <ChartCard title="部门排行" :option="rank('department')" /><ChartCard
        title="项目排行"
        :option="rank('project')"
      /><ChartCard title="模型占比" :option="rank('model')" /></section
  ></template>
  <section class="card records">
    <header class="section-head">
      <h2>最近调用记录</h2>
      <RouterLink class="link" to="/calls">查看全部 →</RouterLink>
    </header>
    <DataTable :fields="fields" :rows="matches"
      ><template #actions="{ row }"
        ><button
          class="link"
          @click="
            () => {
              detail = row
              open = true
            }
          "
        >
          详情
        </button></template
      ></DataTable
    >
  </section>
  <FormDialog v-model="open" title="模拟调用详情" readonly
    ><div v-for="f in fields" :key="f.key" class="field">
      <span>{{ f.label }}</span><strong>{{ detail?.[f.key] }}</strong>
    </div></FormDialog
  >
</template>
