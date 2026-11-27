<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  apiError,
  department,
  provider,
  request,
  type Field,
  type Row,
  type Section,
} from '../api/management'
import FormDialog from '../components/FormDialog.vue'
import { useAuth } from '../stores/auth'

const { section } = defineProps<{ section: Section }>()
const auth = useAuth()
const admin = computed(() => auth.user?.role === 'SUPER_ADMIN')
const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = 15
const term = ref('')
const appliedTerm = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const dialogError = ref('')
const notice = ref('')
const open = ref(false)
const title = ref('')
const form = ref<Record<string, string>>({})
const fields = ref<Field[]>([])
const result = ref<unknown>()
const secret = ref('')
const readonly = ref(false)
let submitAction: ((data: Row) => Promise<void>) | undefined
const roleScopes: Record<string, string> = {
  USER: '本人',
  DEPARTMENT_MANAGER: '本人及授权部门',
  SUPER_ADMIN: '全公司',
}
const states: Record<string, string> = {
  active: '启用',
  disabled: '停用',
  pending: '待领取',
  paused: '已暂停',
  revoked: '已撤销',
  expired: '已过期',
  unknown: '尚待连通验证',
  unavailable: '网关未配置',
}
const stateField: Field = { key: 'state', label: '状态', options: ['active', 'disabled'] }
const userField: Field = { key: 'user_id', label: '用户 ID' }

function show(value: unknown): string {
  if (value == null || value === '') return '—'
  if (Array.isArray(value)) return value.join(', ')
  return states[String(value)] || String(value)
}

async function reload() {
  loading.value = true
  error.value = ''
  try {
    if (section.path === 'roles') {
      rows.value = (await request<string[]>(section.endpoint)).map((role) => ({
        id: role,
        role,
        scope: roleScopes[role],
      }))
      total.value = rows.value.length
    } else {
      const data = await request<{ items: Row[]; total: number }>(
        section.endpoint,
        'GET',
        undefined,
        { page: page.value, size, q: appliedTerm.value },
      )
      rows.value = data.items
      total.value = data.total
    }
  } catch (problem) {
    rows.value = []
    total.value = 0
    error.value = apiError(problem)
  } finally {
    loading.value = false
  }
}

function search() {
  if (loading.value) return
  page.value = 1
  appliedTerm.value = term.value.trim()
  void reload()
}
function pagination(value: number) {
  page.value = value
  void reload()
}
function edit(label: string, schema: Field[], initial: Row, action: (data: Row) => Promise<void>) {
  title.value = label
  result.value = undefined
  secret.value = ''
  dialogError.value = ''
  fields.value = schema
  form.value = Object.fromEntries(
    schema.map(({ key, kind }) => {
      const value = initial[key]
      const display =
        value == null
          ? ''
          : kind === 'ids' && Array.isArray(value)
            ? value.join(', ')
            : String(value)
      return [key, display]
    }),
  )
  submitAction = action
  readonly.value = false
  open.value = true
}
function showResult(label: string, data: unknown) {
  title.value = label
  result.value = data
  secret.value = ''
  dialogError.value = ''
  readonly.value = true
  open.value = true
}
async function submit() {
  if (!submitAction || saving.value) return
  saving.value = true
  dialogError.value = ''
  try {
    const data: Row = {}
    for (const field of fields.value) {
      const raw = form.value[field.key] ?? ''
      const input = field.kind === 'password' ? raw : raw.trim()
      if (!input && !field.optional) throw new Error('请填写' + field.label)
      data[field.key] =
        field.kind === 'ids'
          ? input
              .split(/[,，]/)
              .map((x) => x.trim())
              .filter(Boolean)
          : !input
            ? null
            : field.kind === 'number'
              ? Number(input)
              : field.kind === 'datetime-local'
                ? new Date(input).toISOString()
                : input
    }
    await submitAction(data)
    form.value = {}
    open.value = false
    notice.value = '已保存。'
    await reload()
  } catch (problem) {
    dialogError.value =
      problem instanceof Error && problem.message.startsWith('请填写')
        ? problem.message
        : apiError(problem)
  } finally {
    saving.value = false
  }
}
function resource(row: Row): string {
  return section.endpoint + '/' + String(row.id)
}
function create() {
  if (!section.create) return
  edit('新增' + section.title.replace('管理', ''), section.create, {}, async (data) => {
    await request(section.path === 'keys' ? '/keys/grants' : section.endpoint, 'POST', data)
  })
}
function update(row: Row) {
  if (section.edit)
    edit('编辑' + section.title, section.edit, row, async (data) => {
      await request(resource(row), section.path === 'quotas' ? 'PUT' : 'PATCH', data)
    })
}
async function run(action: () => Promise<void>) {
  notice.value = ''
  error.value = ''
  try {
    await action()
  } catch (problem) {
    error.value = apiError(problem)
  }
}
async function changeState(row: Row, next: string) {
  try {
    await ElMessageBox.confirm('确认' + states[next] + '这条记录？', '确认操作')
  } catch {
    return
  }
  await run(async () => {
    await request(resource(row), 'PATCH', { state: next })
    await reload()
  })
}
async function claim(row: Row) {
  try {
    await ElMessageBox.confirm('确认领取子 Key？原文只展示一次。', '领取子 Key')
  } catch {
    return
  }
  await run(async () => {
    const data = await request<{ key: string }>(resource(row) + '/claim', 'POST')
    showResult('子 Key 领取成功', undefined)
    secret.value = data.key
    await reload()
  })
}
function manageMembers(row: Row, supervisors = false) {
  const suffix = supervisors ? 'supervisors' : 'members'
  edit(
    supervisors ? '设置部门主管授权' : '设置项目成员',
    supervisors ? [userField, stateField] : [userField, department, stateField],
    { state: 'active' },
    async (data) => {
      const { user_id, ...body } = data
      await request(
        resource(row) + '/' + suffix + '/' + encodeURIComponent(String(user_id)),
        'PUT',
        body,
      )
    },
  )
}
function assignRole() {
  edit(
    '分配用户角色',
    [userField, { key: 'role', label: '角色', options: Object.keys(roleScopes) }],
    {},
    async (data) => {
      await request('/users/' + encodeURIComponent(String(data.user_id)), 'PATCH', {
        role: data.role,
      })
    },
  )
}
function addProvider() {
  edit('新增供应商', [{ key: 'code', label: '供应商编码' }], {}, async (data) => {
    await request('/providers', 'POST', data)
  })
}
function providerState() {
  edit('供应商状态', [provider, stateField], {}, async (data) => {
    await request('/providers/' + encodeURIComponent(String(data.provider_id)), 'PATCH', {
      state: data.state,
    })
  })
}
function price(row: Row) {
  edit(
    '追加价格版本',
    [
      { key: 'currency', label: '币种' },
      { key: 'effective_from', label: '生效时间', kind: 'datetime-local' },
      { key: 'unit_tokens', label: '计价 Token 单位', kind: 'number' },
      { key: 'input_price', label: '输入单价' },
      { key: 'output_price', label: '输出单价' },
      { key: 'cache_read_price', label: '缓存读取单价', optional: true },
      { key: 'cache_write_price', label: '缓存写入单价', optional: true },
      { key: 'source_ref', label: '价格来源' },
    ],
    { currency: 'USD', unit_tokens: 1000000 },
    async (data) => {
      await request(resource(row) + '/prices', 'POST', data)
    },
  )
}
function read(label: string, endpoint: string, method = 'GET') {
  return run(async () => showResult(label, await request(endpoint, method)))
}
function clearDialog() {
  secret.value = ''
  form.value = {}
}
onMounted(reload)
</script>

<template>
  <section>
    <h1>{{ section.title }}</h1>
    <p v-if="section.path === 'keys'">平台 Key 通过 FastAPI 调用。业务状态和模型路由就绪状态分别显示。</p>
    <div class="toolbar">
      <form v-if="section.path !== 'roles'" class="toolbar" @submit.prevent="search">
        <label>搜索 <input v-model="term" maxlength="120" /></label>
        <button :disabled="loading">搜索</button>
      </form>
      <button v-if="admin && section.create" class="primary" @click="create">新增</button>
      <button v-if="section.path === 'departments'" @click="read('部门树', '/departments/tree')">
        部门树
      </button>
      <button v-if="section.path === 'roles' && admin" @click="assignRole">分配角色</button>
      <template v-if="section.path === 'models' && admin">
        <button @click="read('供应商', '/providers')">查看供应商</button>
        <button @click="addProvider">新增供应商</button>
        <button @click="providerState">供应商状态</button>
      </template>
    </div>
    <p v-if="error" role="alert">{{ error }} <button @click="reload">重新加载</button></p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="!error && !rows.length">暂无记录</p>
    <div v-if="rows.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th v-for="column in section.columns" :key="column.key">{{ column.label }}</th>
            <th v-if="section.path !== 'roles'">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in section.columns" :key="column.key">{{ show(row[column.key]) }}</td>
            <td v-if="section.path !== 'roles'" class="row-actions">
              <button @click="read('详情', resource(row))">详情</button>
              <button v-if="admin && section.edit" @click="update(row)">编辑</button>
              <button
                v-if="admin && section.states"
                @click="changeState(row, row.state === 'active' ? 'disabled' : 'active')"
              >
                {{ row.state === 'active' ? '停用' : '启用' }}
              </button>
              <template v-if="section.path === 'keys'">
                <button
                  v-if="row.state === 'pending' && row.owner_id === auth.user?.id"
                  @click="claim(row)"
                >
                  领取
                </button>
                <button v-if="admin && row.state === 'active'" @click="changeState(row, 'paused')">
                  暂停
                </button>
                <button v-if="admin && row.state === 'paused'" @click="changeState(row, 'active')">
                  恢复
                </button>
                <button
                  v-if="admin && row.state !== 'revoked'"
                  @click="changeState(row, 'revoked')"
                >
                  撤销
                </button>
              </template>
              <button
                v-if="section.path === 'projects' || section.path === 'departments'"
                @click="read('成员', resource(row) + '/members')"
              >
                成员
              </button>
              <button v-if="admin && section.path === 'projects'" @click="manageMembers(row)">
                设置成员
              </button>
              <button
                v-if="admin && section.path === 'departments'"
                @click="manageMembers(row, true)"
              >
                主管授权
              </button>
              <template v-if="admin && section.path === 'models'">
                <button @click="read('价格版本', resource(row) + '/prices')">价格</button>
                <button @click="price(row)">追加价格</button>
                <button @click="read('连通性测试', resource(row) + '/probe', 'POST')">
                  测试连接
                </button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="section.path !== 'roles' && !error" class="toolbar">
      <button :disabled="loading || page <= 1" @click="pagination(page - 1)">上一页</button>
      <span>第 {{ page }} 页 · 共 {{ total }} 条</span>
      <button :disabled="loading || total <= page * size" @click="pagination(page + 1)">
        下一页
      </button>
    </div>
    <FormDialog
      v-model="open"
      :title="title"
      :readonly="readonly"
      @submit="submit"
      @closed="clearDialog"
    >
      <template v-if="readonly">
        <template v-if="secret"
          ><p>请现在复制保存。可用模型由网关和当前 Key 的权限决定。</p>
          <code>{{ secret }}</code></template
        >
        <pre v-else>{{ JSON.stringify(result, null, 2) }}</pre>
      </template>
      <template v-else>
        <label v-for="field in fields" :key="field.key" class="field"
          >{{ field.label }}
          <select v-if="field.options" v-model="form[field.key]" :required="!field.optional">
            <option value="">请选择</option>
            <option v-for="choice in field.options" :key="choice" :value="choice">
              {{ states[choice] || choice }}
            </option>
          </select>
          <input
            v-else
            v-model="form[field.key]"
            :type="field.kind === 'ids' ? 'text' : field.kind || 'text'"
            :required="!field.optional"
            :minlength="field.kind === 'password' ? 12 : undefined"
            :autocomplete="field.kind === 'password' ? 'new-password' : 'off'"
          />
        </label>
        <p v-if="saving" role="status">正在保存…</p>
        <p v-if="dialogError" role="alert">{{ dialogError }}</p>
      </template>
    </FormDialog>
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-block: 12px;
}
.table-wrap {
  width: 100%;
  overflow-x: auto;
  background: white;
  border-radius: 10px;
}
table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
th,
td {
  padding: 12px;
  border-bottom: 1px solid #e7ecf4;
  overflow-wrap: anywhere;
}
.row-actions {
  min-width: 150px;
}
.row-actions button {
  margin: 2px;
}
pre {
  padding: 12px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 55vh;
  overflow: auto;
}
code {
  user-select: all;
  overflow-wrap: anywhere;
}
</style>
