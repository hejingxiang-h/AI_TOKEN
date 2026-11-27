export interface Field {
  key: string
  label: string
  options?: string[]
  kind?: 'number' | 'email'
}
export interface Section {
  path: string
  title: string
  icon: string
  group: string
  fields: Field[]
  readonly?: boolean
}
const f = (key: string, label: string, options?: string[]): Field => ({ key, label, options })
const number = (key: string, label: string): Field => ({ key, label, kind: 'number' })
const status = f('status', '状态', ['启用', '停用'])
const dept = f('department', '部门', ['研发中心', '数据平台', '产品运营', '安全合规'])
export const sections: Section[] = [
  {
    path: 'calls',
    title: '调用记录',
    icon: 'Tickets',
    group: '审计与风险',
    readonly: true,
    fields: [
      f('name', '请求 ID'),
      f('model', '模型'),
      dept,
      number('tokens', 'Token'),
      number('cost', '费用 USD'),
      f('time', '调用时间'),
      f('status', '状态', ['成功', '失败']),
    ],
  },
  {
    path: 'audit',
    title: '操作日志',
    icon: 'Document',
    group: '审计与风险',
    readonly: true,
    fields: [
      f('name', '操作'),
      f('owner', '操作者'),
      f('target', '对象'),
      f('time', '时间'),
      f('status', '状态', ['成功', '失败']),
    ],
  },
  {
    path: 'alerts',
    title: '风险告警',
    icon: 'Bell',
    group: '审计与风险',
    fields: [
      f('name', '告警名称'),
      f('severity', '等级', ['高', '中', '低']),
      f('owner', '负责人'),
      f('status', '状态', ['待处理', '已确认', '已结案']),
    ],
  },
  {
    path: 'settings',
    title: '系统设置',
    icon: 'Setting',
    group: '系统管理',
    fields: [f('name', '配置项'), f('value', '配置值'), f('description', '说明'), status],
  },
]
export type Row = { id: string } & Record<string, string>
export const departments = ['研发中心', '数据平台', '产品运营', '安全合规']
export const modelNames = ['gpt-4.1-mini', 'deepseek-chat', 'claude-sonnet']
const people = ['林远', '李言', '陈予', '周楠', '王宁', '刘云']
const names: Record<string, string[]> = {
  settings: ['企业时区', '默认币种', '审计保留天数'],
  alerts: ['预算阈值触发', '上游失败率升高', '凭据风险信号'],
  audit: ['更新模型路由', '签发子 Key', '调整项目额度'],
}
export function seed(section: Section): Row[] {
  const list = names[section.path]
  return Array.from({ length: list?.length ?? 23 }, (_, i) => {
    const row: Row = { id: section.path + '-' + i }
    for (const field of section.fields) {
      const value =
        field.options?.[i % field.options.length] ??
        (field.kind === 'number' ? String((i + 1) * 125) : '演示记录 ' + (i + 1))
      row[field.key] = value
    }
    row.name =
      list?.[i] ??
      (section.path === 'users'
        ? people[i % people.length] + ' ' + (i + 1)
        : section.path === 'calls'
          ? 'req_demo_' + String(1024 + i)
          : '演示 ' + section.title + ' ' + (i + 1))
    if ('email' in row) row.email = 'demo' + (i + 1) + '@example.test'
    if ('owner' in row) row.owner = people[i % people.length]!
    if ('model' in row) row.model = modelNames[i % modelNames.length]!
    if ('project' in row) row.project = names.projects![i % 4]!
    if ('time' in row)
      row.time = new Date(Date.now() - i * 2700000).toLocaleString('zh-CN', { hour12: false })
    if (section.path === 'settings') row.value = ['Asia/Shanghai', 'USD', '180'][i]!
    if (section.path === 'roles')
      row.description = ['查看本人资源', '查看被授权部门资源', '管理模拟工作区'][i]!
    if (section.path === 'alerts') row.status = ['待处理', '已确认', '已结案'][i]!
    return row
  })
}
export const groupIcons: Record<string, string> = {}
