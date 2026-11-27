<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiError, request } from '../api/management'
import { useAuth } from '../stores/auth'
import PageHeader from '../components/PageHeader.vue'
import EmptyState from '../components/EmptyState.vue'
import FormDialog from '../components/FormDialog.vue'
import { ElMessageBox } from 'element-plus'

interface Audit {
  id: string
  action: string
  occurred_at: string
  actor_user_id: string | null
  target_type: string
  target_id: string | null
  result: string
  change_summary: Record<string, unknown> | null
}
interface Alert {
  id: string
  kind: string
  status: string
  detected_at: string
  severity: string
  target_type: string
  target_id: string | null
  evidence: Record<string, unknown>
}
const props = defineProps<{ audit?: boolean }>()
const auth = useAuth()
const admin = computed(() => auth.user?.role === 'SUPER_ADMIN')
const size = 20
const page = ref(1)
const total = ref(0)
const rows = ref<(Audit | Alert)[]>([])
const filter = ref('')
const applied = ref('')
const loading = ref(false)
const updating = ref(false)
const error = ref('')
const open = ref(false)
const detail = ref<Record<string, unknown> | null>()
let run = 0
const labels: Record<string, string> = {
  pending: '待处理',
  acknowledged: '已确认',
  resolved: '已解决',
  high: '高',
  warning: '预警',
  quota_threshold: '额度阈值',
  high_frequency: '高频调用',
  high_spend: '短时高额消费',
  provider_errors: '供应商持续报错',
  gateway_error: '网关异常',
  invalid_key: '无效 Key 高频',
  invoice_mismatch: '供应商账单差异',
  usage_write_error: '用量写入异常',
  settlement_failure: '结算异常',
  success: '成功',
}
const show = (value: string) => labels[value] ?? value
async function load() {
  const active = ++run
  error.value = ''
  loading.value = true
  try {
    const params = {
      page: page.value,
      size,
      ...(props.audit ? { q: applied.value } : applied.value ? { status: applied.value } : {}),
    }
    const result = await request<{ items: (Audit | Alert)[]; total: number }>(
      props.audit ? '/audit-events' : '/alerts',
      'GET',
      undefined,
      params,
    )
    if (active !== run) return
    rows.value = result.items
    total.value = result.total
  } catch (problem) {
    if (active !== run) return
    error.value = apiError(problem)
    rows.value = []
  } finally {
    if (active === run) loading.value = false
  }
}
watch([page, applied], load, { immediate: true })
function search() {
  page.value = 1
  applied.value = filter.value.trim()
}
function details(row: Audit | Alert) {
  detail.value = 'change_summary' in row ? row.change_summary : row.evidence
  open.value = true
}
async function change(row: Alert, status: string) {
  try {
    await ElMessageBox.confirm('将告警标为' + show(status) + '？', '确认操作')
  } catch {
    return
  }
  updating.value = true
  try {
    await request('/alerts/' + row.id, 'PATCH', { status })
    await load()
  } catch (problem) {
    error.value = apiError(problem)
  } finally {
    updating.value = false
  }
}
</script>

<template>
  <PageHeader :title="audit ? '操作日志' : '风险告警'" />
  <p v-if="!audit">告警供人工核查。风险标记不代表违规结论。</p>
  <section class="card risk-panel">
    <form class="actions" @submit.prevent="search">
      <label v-if="audit">操作类型 <input v-model="filter" maxlength="60" /></label>
      <label v-else
        >处理状态
        <select v-model="filter">
          <option value="">全部</option>
          <option value="pending">待处理</option>
          <option value="acknowledged">已确认</option>
          <option value="resolved">已解决</option>
        </select></label
      >
      <button type="submit">筛选</button>
    </form>
    <p v-if="error" role="alert">{{ error }} <button @click="load">重试</button></p>
    <p v-else-if="loading" role="status">正在加载…</p>
    <EmptyState v-else-if="!rows.length" title="暂无记录" description="可调整筛选条件。" />
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>类型</th>
            <th>对象</th>
            <th>操作者 / 级别</th>
            <th>结果 / 状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>
              {{
                new Date('occurred_at' in row ? row.occurred_at : row.detected_at).toLocaleString(
                  'zh-CN',
                )
              }}
            </td>
            <td>{{ 'action' in row ? row.action : show(row.kind) }}</td>
            <td>{{ row.target_type }} {{ row.target_id || '—' }}</td>
            <td>{{ 'actor_user_id' in row ? row.actor_user_id || '—' : show(row.severity) }}</td>
            <td>{{ show('result' in row ? row.result : row.status) }}</td>
            <td>
              <button @click="details(row)">摘要</button>
              <template v-if="admin && 'status' in row">
                <button
                  v-if="row.status === 'pending'"
                  :disabled="updating"
                  @click="change(row, 'acknowledged')"
                >
                  确认
                </button>
                <button
                  v-if="row.status !== 'resolved'"
                  :disabled="updating"
                  @click="change(row, 'resolved')"
                >
                  解决
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="!error && total" class="actions">
      <button :disabled="page <= 1 || loading" @click="page--">上一页</button>
      <span>第 {{ page }} 页 · {{ total }} 条</span>
      <button :disabled="page * size >= total || loading" @click="page++">下一页</button>
    </div>
  </section>
  <FormDialog v-model="open" title="记录摘要" readonly>
    <pre>{{ detail ? JSON.stringify(detail, null, 2) : '无摘要' }}</pre>
  </FormDialog>
</template>
<style scoped>
.risk-panel {
  padding: 16px;
}
.table-wrap {
  overflow: auto;
  margin: 12px 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
th,
td {
  padding: 8px;
  border-bottom: 1px solid #e7ecf4;
}
pre {
  overflow: auto;
  max-height: 320px;
}
</style>
