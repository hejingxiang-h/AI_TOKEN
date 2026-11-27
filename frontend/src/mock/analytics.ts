import { departments, modelNames, type Row } from './catalog'
const today = new Date()
today.setHours(0, 0, 0, 0)
const projects = ['智能研发助手', '知识检索', '数据分析平台', '工单助手']
export const activity = Array.from({ length: 31 * 12 }, (_, i) => {
  const date = new Date(today)
  date.setDate(date.getDate() - Math.floor(i / 12))
  date.setHours(11 - (i % 12) + 1)
  const input = 1400 + ((i * 1097) % 65000),
    output = 350 + ((i * 401) % 22000)
  return {
    date,
    input,
    output,
    cents: 2 + ((i * 11) % 73),
    department: departments[i % 4]!,
    project: projects[(i + Math.floor(i / 12)) % 4]!,
    model: modelNames[i % 3]!,
    user: i % 27,
    key: i % 15,
    failed: i % 19 === 0,
  }
})
export const recent = activity.map((a, i): Row => ({
  id: String(i),
  name: 'req_demo_' + (1024 + i),
  model: a.model,
  department: a.department,
  tokens: String(a.input + a.output),
  cost: (a.cents / 100).toFixed(2),
  time: a.date.toLocaleString('zh-CN', { hour12: false }),
  status: a.failed ? '失败' : '成功',
}))
export const number = new Intl.NumberFormat('zh-CN')
export const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
export const dateValue = (d: Date) =>
  [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, '0'),
    String(d.getDate()).padStart(2, '0'),
  ].join('-')
export function bounds(preset: string, start: string, end: string) {
  const from = new Date(today),
    to = new Date(today)
  if (preset === '昨天') {
    from.setDate(from.getDate() - 1)
    to.setDate(to.getDate() - 1)
  }
  if (preset === '最近7天' || preset === '最近30天')
    from.setDate(from.getDate() - (preset === '最近7天' ? 6 : 29))
  if (preset === '本月') from.setDate(1)
  return preset === '自定义' ? [start, end] : [dateValue(from), dateValue(to)]
}
