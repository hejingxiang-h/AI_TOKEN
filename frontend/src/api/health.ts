import type { HealthResponse } from '../types/health'
import { ApiError } from '../utils/api-error'
import { http } from './http'

export async function getReadiness(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>('/health/ready', {
    validateStatus: (status) => status === 200 || status === 503,
  })
  if (!data?.checks?.postgresql || !data?.checks?.redis) {
    throw new ApiError('健康检查未返回有效结果，请重试。')
  }
  return data
}
