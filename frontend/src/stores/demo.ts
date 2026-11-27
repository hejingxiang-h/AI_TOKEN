import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sections, seed, type Row } from '../mock/catalog'

const key = 'gateway-demo-records-v1'
export const useDemo = defineStore('demo', () => {
  const records = ref<Record<string, Row[]>>({})
  const error = ref('')
  try {
    records.value = JSON.parse(localStorage.getItem(key) ?? '{}') ?? {}
  } catch {
    error.value = '无法读取本地演示数据，可重置后重试。'
  }
  function rows(path: string): Row[] {
    return records.value[path] ?? seed(sections.find((section) => section.path === path)!)
  }
  function replace(path: string, next: Row[]) {
    try {
      const draft = { ...records.value, [path]: next }
      localStorage.setItem(key, JSON.stringify(draft))
      records.value = draft
      error.value = ''
      return true
    } catch {
      error.value = '无法保存演示数据，请检查浏览器存储权限。'
      return false
    }
  }
  function reset() {
    try {
      localStorage.removeItem(key)
      records.value = {}
      error.value = ''
    } catch {
      error.value = '无法重置演示数据。'
    }
  }
  return { rows, replace, error, reset }
})
