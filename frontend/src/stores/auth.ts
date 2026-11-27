import axios from 'axios'
import { defineStore } from 'pinia'
import { ref } from 'vue'

interface User {
  id: string
  role: 'USER' | 'DEPARTMENT_MANAGER' | 'SUPER_ADMIN'
  display_name: string
  login_normalized: string
}
interface Tokens {
  access_token: string
}

const authApi = axios.create({ baseURL: '/api/v1', withCredentials: true, timeout: 7000 })

export const useAuth = defineStore('auth', () => {
  const user = ref<User>()
  const accessToken = ref('')
  let attempted = false
  let renewing: Promise<void> | undefined

  async function accept(tokens: Tokens): Promise<void> {
    accessToken.value = tokens.access_token
    try {
      const response = await authApi.get<User>('/me', { headers: headers() })
      user.value = response.data
    } catch (error) {
      accessToken.value = ''
      user.value = undefined
      throw error
    }
  }

  function headers() {
    return { Authorization: 'Bearer ' + accessToken.value }
  }

  async function login(loginName: string, password: string): Promise<void> {
    attempted = true
    const { data } = await authApi.post<Tokens>('/auth/login', { login: loginName, password })
    await accept(data)
  }

  async function restore(): Promise<void> {
    if (attempted) return
    attempted = true
    await refreshSession()
  }
  async function renew() {
    try {
      const { data } = await authApi.post<Tokens>('/auth/refresh')
      await accept(data)
    } catch {
      accessToken.value = ''
      user.value = undefined
    }
  }

  async function refreshSession() {
    renewing ??= renew().finally(() => {
      renewing = undefined
    })
    return renewing
  }
  async function logout(): Promise<void> {
    await authApi.post('/auth/logout', undefined, { headers: headers() })
    user.value = undefined
    accessToken.value = ''
  }

  async function changePassword(current: string, replacement: string): Promise<void> {
    await authApi.post(
      '/auth/password',
      {
        current_password: current,
        new_password: replacement,
      },
      { headers: headers() },
    )
    user.value = undefined
    accessToken.value = ''
  }
  return { user, accessToken, restore, login, logout, changePassword, headers, refreshSession }
})
