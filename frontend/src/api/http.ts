import axios from 'axios'

import { describeApiError } from '../utils/api-error'

export const http = axios.create({
  timeout: 6000,
  headers: { Accept: 'application/json' },
})

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(describeApiError(error)),
)
