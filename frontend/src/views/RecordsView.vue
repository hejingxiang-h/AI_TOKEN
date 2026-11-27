<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { Section, Row } from '../mock/catalog'
import { useDemo } from '../stores/demo'
import PageHeader from '../components/PageHeader.vue'
import DataTable from '../components/DataTable.vue'
import SearchForm from '../components/SearchForm.vue'
import FormDialog from '../components/FormDialog.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
const props = defineProps<{ section: Section }>()
const store = useDemo()
const query = ref(''),
  status = ref(''),
  appliedQuery = ref(''),
  appliedStatus = ref('')
const page = ref(1),
  size = ref(10),
  loading = ref(true)
const open = ref(false),
  confirm = ref(false),
  resetConfirm = ref(false)
const mode = ref<'create' | 'edit' | 'detail'>('create')
const selected = ref<Row>(),
  form = ref<Record<string, string>>({}),
  errors = ref<Record<string, string>>({})
const notice = ref('')
const all = computed(() => store.rows(props.section.path))
const options = computed(() => props.section.fields.find((f) => f.key === 'status')?.options ?? [])
const filtered = computed(() =>
  all.value.filter(
    (r) =>
      (!appliedStatus.value || r.status === appliedStatus.value) &&
      Object.values(r).some((v) => v.toLowerCase().includes(appliedQuery.value)),
  ),
)
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / size.value)))
const visible = computed(() =>
  filtered.value.slice((page.value - 1) * size.value, page.value * size.value),
)
onMounted(() => window.setTimeout(() => (loading.value = false), 180))
function search() {
  page.value = 1
  appliedQuery.value = query.value.trim().toLowerCase()
  appliedStatus.value = status.value
}
function resetSearch() {
  query.value = ''
  status.value = ''
  search()
}
function show(next: typeof mode.value, row?: Row) {
  mode.value = next
  selected.value = row
  errors.value = {}
  form.value = Object.fromEntries(
    props.section.fields.map((f) => [f.key, row?.[f.key] ?? f.options?.[0] ?? '']),
  )
  open.value = true
}
function save() {
  errors.value = {}
  const values: Record<string, string> = {}
  for (const field of props.section.fields) {
    const value = (form.value[field.key] ?? '').trim()
    values[field.key] = value
    if (!value) errors.value[field.key] = '请填写' + field.label
    else if (field.kind === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
      errors.value[field.key] = '请输入有效邮箱'
    else if (field.kind === 'number' && (!Number.isFinite(Number(value)) || Number(value) < 0))
      errors.value[field.key] = '请输入非负数字'
  }
  if (Object.keys(errors.value).length) return
  const item = { ...values, id: selected.value?.id ?? crypto.randomUUID() }
  const records =
    mode.value === 'edit'
      ? all.value.map((r) => (r.id === item.id ? item : r))
      : [item, ...all.value]
  if (store.replace(props.section.path, records)) {
    open.value = false
    notice.value = '已保存演示记录'
    resetSearch()
  }
}
function remove() {
  if (
    store.replace(
      props.section.path,
      all.value.filter((r) => r.id !== selected.value?.id),
    )
  ) {
    confirm.value = false
    page.value = Math.min(page.value, pages.value)
    notice.value = '已删除演示记录'
  }
}
</script>
<template>
  <PageHeader :title="section.title" description="使用浏览器本地保存的模拟记录。"
    ><button v-if="section.path === 'settings'" @click="resetConfirm = true">重置演示数据</button
    ><button v-if="!section.readonly" class="primary" @click="show('create')">
      ＋ 新增
    </button></PageHeader
  >
  <p v-if="store.error" role="alert" class="failure">{{ store.error }}</p>
  <p v-if="notice" role="status" class="notice">{{ notice }}</p>
  <section class="card records">
    <SearchForm
      v-model:query="query"
      v-model:status="status"
      :options="options"
      @search="search"
      @reset="resetSearch"
    />
    <DataTable :fields="section.fields" :rows="visible" :loading="loading"
      ><template #actions="{ row }"
        ><button class="link" @click="show('detail', row)">详情</button
        ><template v-if="!section.readonly"
          ><button class="link" @click="show('edit', row)">编辑</button
          ><button
            class="link danger"
            @click="
              () => {
                selected = row
                confirm = true
              }
            "
          >
            删除
          </button></template
        ></template
      ></DataTable
    >
    <div class="pagination">
      <span>共 {{ filtered.length }} 条</span
      ><label
        >每页
        <select v-model.number="size" @change="page = 1">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select></label
      ><button :disabled="page <= 1" @click="page--">上一页</button
      ><span>{{ page }} / {{ pages }}</span
      ><button :disabled="page >= pages" @click="page++">下一页</button>
    </div>
  </section>
  <FormDialog
    v-model="open"
    :title="(mode === 'create' ? '新增' : mode === 'edit' ? '编辑' : '详情 · ') + section.title"
    :readonly="mode === 'detail'"
    @submit="save"
  >
    <p v-if="store.error" role="alert" class="failure">{{ store.error }}</p>
    <div v-for="field in section.fields" :key="field.key" class="field">
      <label :for="'field-' + field.key">{{ field.label }}</label><strong
        v-if="mode === 'detail'"
        >{{ form[field.key] }}</strong
      ><select v-else-if="field.options" :id="'field-' + field.key" v-model="form[field.key]">
        <option v-for="value in field.options" :key="value">{{ value }}</option></select
      ><input
        v-else
        :id="'field-' + field.key"
        v-model="form[field.key]"
        :aria-invalid="Boolean(errors[field.key])"
        :inputmode="field.kind === 'number' ? 'decimal' : undefined"
      /><small v-if="errors[field.key]" role="alert">{{ errors[field.key] }}</small>
    </div>
  </FormDialog>
  <ConfirmDialog
    v-model="confirm"
    title="删除演示记录"
    :description="'确认删除「' + (selected?.name ?? '') + '」？'"
    @confirm="remove"
  />
  <ConfirmDialog
    v-model="resetConfirm"
    title="重置演示数据"
    description="清除当前浏览器保存的演示改动，恢复初始记录。"
    @confirm="
      () => {
        store.reset()
        resetConfirm = false
        resetSearch()
        notice = '已恢复初始演示数据'
      }
    "
  />
</template>
