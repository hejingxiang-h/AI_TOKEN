<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import { apiError, request } from '../api/management'
import type { Breakdown, Group, Summary, UsageDetail, UsagePage } from '../api/usage'
import PageHeader from '../components/PageHeader.vue'
import StatCard from '../components/StatCard.vue'
import EmptyState from '../components/EmptyState.vue'
import FormDialog from '../components/FormDialog.vue'

const props = defineProps<{ statistics?: boolean; recordsOnly?: boolean }>()
const ChartCard = defineAsyncComponent(() => import('../components/ChartCard.vue'))
const ranges = [
  ['today', '今天'],
  ['yesterday', '昨天'],
  ['7d', '最近7天'],
  ['30d', '最近30天'],
  ['month', '本月'],
  ['custom', '自定义'],
] as const
const dimensions = [
  ['department', '部门'],
  ['project', '项目'],
  ['user', '用户'],
  ['model', '模型'],
  ['provider', '供应商'],
  ['key', 'API Key'],
] as const
type Preset = (typeof ranges)[number][0]
type Dimension = (typeof dimensions)[number][0]
const title = computed(() =>
  props.recordsOnly ? '调用记录' : props.statistics ? 'Token 统计' : '首页工作台',
)
const preset = ref<Preset>('today')
const applied = ref<Preset>('today')
const from = ref('')
const to = ref('')
const custom = ref<{ start: string; end: string }>()
const dimension = ref<Dimension>('department')
const filter = ref('')
const page = ref(1)
const size = 15
const filters = computed(() => ({
  period: applied.value,
  ...(applied.value === 'custom' ? custom.value : {}),
  ...(filter.value ? { [dimension.value + '_id']: filter.value } : {}),
}))
const summary = ref<Summary>()
const daily = ref<Group[]>([])
const groups = ref<Partial<Record<Dimension, Group[]>>>({})
const records = ref<UsagePage>()
const loading = ref(false)
const error = ref('')
const validation = ref('')
const currency = ref('')
const detail = ref<UsageDetail>()
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
let run = 0
let detailRun = 0

async function load() {
  const current = ++run
  loading.value = true
  error.value = ''
  const query = filters.value
  try {
    const [overview, list, trend, ...parts] = await Promise.all([
      request<Summary>(
        props.statistics || props.recordsOnly ? '/usage/summary' : '/dashboard/overview',
        'GET',
        undefined,
        query,
      ),
      request<UsagePage>('/usage/records', 'GET', undefined, { ...query, page: page.value, size }),
      props.recordsOnly
        ? Promise.resolve(undefined)
        : request<Breakdown>('/usage/trend', 'GET', undefined, query),
      ...dimensions.map(([key]) =>
        request<Breakdown>(
          '/usage/by-' + key,
          'GET',
          undefined,
          props.recordsOnly
            ? { period: query.period, ...(query.period === 'custom' ? custom.value : {}) }
            : query,
        ),
      ),
    ])
    if (current !== run) return
    summary.value = overview
    records.value = list
    daily.value = trend?.items ?? []
    groups.value = Object.fromEntries(parts.map((part, i) => [dimensions[i]![0], part.items]))
    if (!(currency.value in overview.metrics.costs))
      currency.value = Object.keys(overview.metrics.costs)[0] ?? ''
  } catch (problem) {
    if (current !== run) return
    summary.value = undefined
    records.value = undefined
    daily.value = []
    groups.value = {}
    error.value = apiError(problem)
  } finally {
    if (current === run) loading.value = false
  }
}
watch([filters, page], load, { immediate: true })

function choose(next: Preset) {
  preset.value = next
  validation.value = ''
  if (next !== 'custom') {
    page.value = 1
    applied.value = next
  }
}
function apply() {
  if (!from.value || !to.value || from.value > to.value) {
    validation.value = '请选择有效的日期范围。'
    return
  }
  validation.value = ''
  page.value = 1
  custom.value = { start: from.value, end: to.value }
  applied.value = 'custom'
}
function changeDimension() {
  page.value = 1
  filter.value = ''
}
function changeFilter() {
  page.value = 1
}

async function openDetail(id: string) {
  const current = ++detailRun
  detail.value = undefined
  detailOpen.value = true
  detailLoading.value = true
  detailError.value = ''
  try {
    const result = await request<UsageDetail>('/usage/records/' + encodeURIComponent(id))
    if (current === detailRun) detail.value = result
  } catch (problem) {
    if (current === detailRun) detailError.value = apiError(problem)
  } finally {
    if (current === detailRun) detailLoading.value = false
  }
}

const format = new Intl.NumberFormat('zh-CN')
const count = (v: number | null | undefined) => (v == null ? '—' : format.format(v))
const amount = (v: string) => (v.includes('.') ? v.replace(/0+$/, '').replace(/\.$/, '') : v)
const percent = (v: string | null) => (v == null ? '—' : (Number(v) * 100).toFixed(2) + '%')
const statuses: Record<string, string> = {
  success: '成功',
  dispatching: '进行中',
  released: '已释放',
  settled: '已结算',
  reserved: '已预留',
  review: '待核对',
  upstream_timeout: '上游超时',
  upstream_error: '上游错误',
  interrupted: '流式中断',
  client_disconnected: '客户端断开',
  budget_denied: '额度拒绝',
  rate_denied: '限流拒绝',
  upstream_rejected: '上游拒绝',
  not_dispatched: '未发送',
}
function status(value: string) {
  return statuses[value] ?? value
}
function dateTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'short',
    timeStyle: 'medium',
    timeZone: summary.value?.window.timezone ?? 'UTC',
  }).format(new Date(value))
}

const cards = computed(() => {
  const m = summary.value?.metrics
  if (!m) return []
  return [
    ['总 Token', count(m.total_tokens)],
    ['输入 Token', count(m.input_tokens)],
    ['输出 Token', count(m.output_tokens)],
    ['缓存 Token', count(m.cache_tokens)],
    [
      '已结算费用',
      Object.entries(m.costs)
        .map(([unit, value]) => unit + ' ' + amount(value))
        .join(' · ') || '—',
    ],
    ['调用次数', count(m.calls)],
    ['成功次数', count(m.successes)],
    ['失败次数', count(m.failures)],
    ['成功率', percent(m.success_rate)],
    ['活跃用户', count(m.active_users)],
    ['活跃 Key', count(m.active_keys)],
    ['平均响应时间', m.average_response_ms === null ? '—' : amount(m.average_response_ms) + ' ms'],
    ['未结算', count(m.unsettled)],
    ['用量未知', count(m.unknown_usage)],
  ]
})
function line(metric: 'tokens' | 'cost' | 'rate'): EChartsCoreOption {
  const values = daily.value.map(({ metrics: m }) => {
    if (metric === 'tokens') return m.total_tokens
    if (metric === 'rate') return m.success_rate == null ? null : Number(m.success_rate) * 100
    return currency.value in m.costs ? Number(m.costs[currency.value]) : null
  })
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 70, right: 24, top: 16, bottom: 30 },
    xAxis: { type: 'category', data: daily.value.map((x) => x.label) },
    yAxis: {
      type: 'value',
      ...(metric === 'rate' ? { max: 100, axisLabel: { formatter: '{value}%' } } : {}),
    },
    series: [{ type: 'line', data: values }],
  }
}
function rank(key: Dimension): EChartsCoreOption {
  const items = (groups.value[key] ?? []).slice(0, 10).reverse()
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 100, right: 32, top: 10, bottom: 24 },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: items.map((i) => i.label),
      axisLabel: { width: 80, overflow: 'truncate' },
    },
    series: [{ type: 'bar', data: items.map((i) => i.metrics.total_tokens) }],
  }
}
function pie(key: 'model' | 'provider'): EChartsCoreOption {
  const data = (groups.value[key] ?? []).flatMap((item) => {
    const value = key === 'model' ? item.metrics.total_tokens : item.metrics.costs[currency.value]
    return value == null || Number(value) <= 0 ? [] : [{ name: item.label, value: Number(value) }]
  })
  return { tooltip: { trigger: 'item' }, series: [{ type: 'pie', radius: ['42%', '69%'], data }] }
}
</script>

<template>
  <PageHeader :title="title" description="按企业时区查看模型调用、Token 用量和已结算费用。">
    <RouterLink v-if="!recordsOnly" class="button" to="/calls">查看调用记录</RouterLink>
  </PageHeader>
  <section class="card time-filter">
    <div class="actions">
      <button
        v-for="[id, label] in ranges"
        :key="id"
        :aria-pressed="preset === id"
        :class="{ chosen: preset === id }"
        @click="choose(id)"
      >
        {{ label }}
      </button>
    </div>
    <span v-if="summary"
      >{{ summary.window.start }} 至 {{ summary.window.end }} · {{ summary.window.timezone }}</span
    >
    <form v-if="preset === 'custom'" class="custom-range" @submit.prevent="apply">
      <label>开始日期 <input v-model="from" type="date" required /></label>
      <label>结束日期 <input v-model="to" type="date" required /></label>
      <button class="primary">应用</button>
      <p v-if="validation" role="alert">{{ validation }}</p>
    </form>
    <div class="actions">
      <label
        >筛选维度
        <select v-model="dimension" @change="changeDimension">
          <option v-for="[id, label] in dimensions" :key="id" :value="id">{{ label }}</option>
        </select></label
      >
      <label
        >筛选对象
        <select v-model="filter" @change="changeFilter">
          <option value="">全部可见</option>
          <option v-for="item in groups[dimension]" :key="item.id" :value="item.id">
            {{ item.label }}
          </option>
        </select></label
      >
    </div>
  </section>
  <p v-if="loading" role="status">正在加载真实用量…</p>
  <p v-else-if="error" role="alert">{{ error }} <button @click="load">重试</button></p>
  <template v-else-if="summary">
    <section v-if="!recordsOnly" class="metrics">
      <StatCard
        v-for="[label, value] in cards"
        :key="label"
        :label="label!"
        :value="value!"
        note=""
        icon=""
      />
    </section>
    <EmptyState
      v-if="!summary.metrics.calls"
      title="该范围暂无调用"
      description="请尝试其他日期或筛选条件。"
    />
    <template v-else-if="!recordsOnly">
      <label v-if="currency"
        >图表费用币种
        <select v-model="currency">
          <option v-for="unit in Object.keys(summary.metrics.costs)" :key="unit">{{ unit }}</option>
        </select></label
      >
      <section class="trends">
        <ChartCard title="Token 趋势" :option="line('tokens')" />
        <ChartCard v-if="currency" :title="'费用趋势 · ' + currency" :option="line('cost')" />
        <ChartCard title="成功率" :option="line('rate')" />
      </section>
      <section class="rankings">
        <ChartCard title="部门排行" :option="rank('department')" />
        <ChartCard title="项目排行" :option="rank('project')" />
        <ChartCard title="用户排行" :option="rank('user')" />
        <ChartCard title="模型占比" :option="pie('model')" />
        <ChartCard
          v-if="currency"
          :title="'供应商费用占比 · ' + currency"
          :option="pie('provider')"
        />
      </section>
    </template>
    <section v-if="records?.items.length" class="card usage-records">
      <h2>调用明细</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>供应商 / 模型</th>
              <th>Token</th>
              <th>费用</th>
              <th>状态</th>
              <th>结算</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in records.items" :key="row.id">
              <td>{{ dateTime(row.started_at) }}</td>
              <td>{{ row.provider }} / {{ row.model }}</td>
              <td>{{ row.normalized_usage ? count(row.normalized_usage.total) : '未知' }}</td>
              <td>
                {{
                  row.platform_cost == null ? '—' : row.currency + ' ' + amount(row.platform_cost)
                }}
              </td>
              <td>{{ status(row.status) }}</td>
              <td>{{ status(row.settlement) }}</td>
              <td><button @click="openDetail(row.id)">查看详情</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="actions">
        <button :disabled="page <= 1" @click="page--">上一页</button>
        <span>第 {{ page }} 页 · {{ records.total }} 条</span>
        <button :disabled="page * size >= records.total" @click="page++">下一页</button>
      </div>
    </section>
  </template>
  <FormDialog v-model="detailOpen" title="调用详情" readonly>
    <p v-if="detailLoading" role="status">正在加载…</p>
    <p v-else-if="detailError" role="alert">{{ detailError }}</p>
    <dl v-else-if="detail" class="detail">
      <dt>请求 ID</dt>
      <dd>{{ detail.id }}</dd>
      <dt>用户 / 部门 / 项目</dt>
      <dd>{{ detail.user_id }} / {{ detail.department_id }} / {{ detail.project_id }}</dd>
      <dt>API Key ID</dt>
      <dd>{{ detail.key_id }}</dd>
      <dt>结算状态</dt>
      <dd>{{ status(detail.settlement) }}</dd>
      <dt>耗时</dt>
      <dd>{{ detail.duration_ms == null ? '—' : detail.duration_ms + ' ms' }}</dd>
      <dt>来源 IP</dt>
      <dd>{{ detail.source_ip || '—' }}</dd>
      <dt>客户端类型</dt>
      <dd>{{ detail.client_type || '未知' }}</dd>
      <dt>风险状态</dt>
      <dd>{{ detail.risk_state === 'flagged' ? '待核查' : '未标记' }}</dd>
      <dt>价格版本</dt>
      <dd>{{ detail.price_id }}</dd>
      <dt>用量来源</dt>
      <dd>{{ detail.usage_source || '未知' }}</dd>
      <dt>计量字段</dt>
      <dd>
        <pre>{{ detail.raw_usage ? JSON.stringify(detail.raw_usage, null, 2) : '无可用计量' }}</pre>
      </dd>
    </dl>
  </FormDialog>
</template>

<style scoped>
.usage-records {
  margin-top: 16px;
  padding: 16px;
}
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
}
td,
th {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid #e7ecf4;
}
.detail dd {
  overflow-wrap: anywhere;
  margin: 0 0 10px;
}
.detail pre {
  max-height: 200px;
  overflow: auto;
}
</style>
