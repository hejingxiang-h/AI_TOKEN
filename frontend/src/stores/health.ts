import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getReadiness } from '../api/health'
import type { HealthResponse } from '../types/health'
import { ApiError } from '../utils/api-error'

export const useHealthStore = defineStore('health', () => {
  const result = ref<HealthResponse>()
  const checkedAt = ref<Date>()
  const loading = ref(false)
  const error = ref('')

  async function refresh(): Promise<void> {
    if (loading.value) return

    loading.value = true
    error.value = ''
    try {
      result.value = await getReadiness()
      checkedAt.value = new Date()
    } catch (cause) {
      error.value = cause instanceof ApiError ? cause.message : '系统健康状态暂不可用。'
    } finally {
      loading.value = false
    }
  }

  return { result, checkedAt, loading, error, refresh }
})
