import axios from 'axios'
import { useAuth } from '../stores/auth'

export type Row = Record<string, unknown>
export interface Field {
  key: string
  label: string
  kind?: 'password' | 'number' | 'datetime-local' | 'ids'
  options?: readonly string[]
  optional?: boolean
}
export interface Section {
  path: string
  endpoint: string
  title: string
  icon: string
  group: string
  columns: Field[]
  create?: Field[]
  edit?: Field[]
  states?: readonly string[]
}

const roles = ['USER', 'DEPARTMENT_MANAGER', 'SUPER_ADMIN']
const onOff = ['active', 'disabled']
const f = (key: string, label: string, props?: Omit<Field, 'key' | 'label'>): Field => ({
  key,
  label,
  ...props,
})
const state = f('state', '状态')
const name = f('name', '名称')
const code = f('code', '编码')
export const department = f('department_id', '部门 ID')
export const models = f('model_ids', '模型 ID 白名单（逗号分隔）', { kind: 'ids' })
export const provider = f('provider_id', '供应商 ID')
export const quotas = [
  f('scope', '范围', { options: ['enterprise', 'department', 'project', 'user', 'key'] }),
  f('target_id', '对象 ID（企业范围留空）', { optional: true }),
  f('daily_amount', '每日额度 (USD)'),
  f('monthly_amount', '每月额度 (USD)'),
  f('rpm', '每分钟请求上限', { kind: 'number' }),
  f('warning_percent', '预警百分比'),
  { ...models, optional: true },
]
const login = f('login_normalized', '登录名')
const display = f('display_name', '姓名')
const role = f('role', '角色', { options: roles })
const primaryDepartment = f('primary_department_id', '所属部门 ID', { optional: true })
const parent = f('parent_id', '上级部门 ID', { optional: true })
const owner = f('owner_id', '负责人 ID', { optional: true })
const alias = f('alias', '模型别名')
const modelKey = f('label', 'Key 名称')
export const management: Section[] = [
  {
    path: 'users',
    endpoint: '/users',
    title: '用户管理',
    icon: 'Users',
    group: '组织管理',
    columns: [login, display, role, primaryDepartment, state],
    create: [
      { ...login, key: 'login' },
      display,
      f('password', '初始密码', { kind: 'password' }),
      role,
      primaryDepartment,
    ],
    edit: [display, role, primaryDepartment],
    states: onOff,
  },
  {
    path: 'departments',
    endpoint: '/departments',
    title: '部门管理',
    icon: 'OfficeBuilding',
    group: '组织管理',
    columns: [code, name, parent, owner, state],
    create: [code, name, parent, owner],
    edit: [name, parent, owner],
    states: onOff,
  },
  {
    path: 'projects',
    endpoint: '/projects',
    title: '项目管理',
    icon: 'Folder',
    group: '组织管理',
    columns: [code, name, state],
    create: [code, name],
    edit: [name],
    states: onOff,
  },
  {
    path: 'keys',
    endpoint: '/keys',
    title: 'API Key 管理',
    icon: 'Key',
    group: '模型与额度',
    columns: [
      modelKey,
      f('hint', 'Key 前缀'),
      f('gateway_status', '模型网关状态'),
      state,
      f('expires_at', '有效期'),
      f('last_used_at', '最近使用'),
    ],
    create: [
      modelKey,
      f('owner_id', '所有人 ID'),
      department,
      f('project_id', '项目 ID'),
      models,
      f('expires_at', '有效期', { kind: 'datetime-local' }),
    ],
  },
  {
    path: 'quotas',
    endpoint: '/quotas',
    title: '配额管理',
    icon: 'Coin',
    group: '模型与额度',
    columns: quotas.slice(0, 6),
    create: quotas,
    edit: quotas,
  },
  {
    path: 'models',
    endpoint: '/model-routes',
    title: '模型管理',
    icon: 'Cpu',
    group: '模型与额度',
    columns: [alias, provider, f('protocol', '协议'), state],
    states: onOff,
    create: [
      provider,
      alias,
      f('upstream_model', '上游模型'),
      f('protocol', '协议', { options: ['chat_completions', 'messages', 'responses'] }),
    ],
  },
  {
    path: 'roles',
    endpoint: '/roles',
    title: '角色权限',
    icon: 'Lock',
    group: '系统管理',
    columns: [f('role', '角色'), f('scope', '数据范围')],
  },
]
const client = axios.create({ baseURL: '/api/v1', timeout: 12000, withCredentials: true })
export async function request<T>(
  path: string,
  method = 'GET',
  data?: Row,
  params?: Row,
): Promise<T> {
  const auth = useAuth()
  const send = () => client.request<T>({ url: path, method, data, params, headers: auth.headers() })
  try {
    return (await send()).data
  } catch (error) {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) throw error
    await auth.refreshSession()
    if (!auth.user) throw error
    return (await send()).data
  }
}
export function apiError(error: unknown): string {
  if (!axios.isAxiosError(error)) return '无法完成请求。'
  if (error.response?.status === 401) return '会话已失效，请重新登录。'
  if (error.response?.status === 403) return '当前角色没有此操作权限。'
  return error.response?.data?.error?.message || '服务暂时不可用，请重试。'
}
