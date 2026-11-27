import { isAxiosError } from 'axios'

export class ApiError extends Error {}

export function describeApiError(error: unknown): ApiError {
  if (isAxiosError(error) && ['ECONNABORTED', 'ETIMEDOUT'].includes(error.code || '')) {
    return new ApiError('健康检查请求超时，请重试。')
  }
  return new ApiError('暂时无法获取健康状态，请检查后端连接后重试。')
}
