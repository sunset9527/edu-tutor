import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '../api/client'

export interface AuthUser {
  id: number
  username: string
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('edututor_token') || '')
  const user = ref<AuthUser | null>(
    JSON.parse(localStorage.getItem('edututor_user') || 'null')
  )

  function setAuth(t: string, u: AuthUser) {
    token.value = t
    user.value = u
    localStorage.setItem('edututor_token', t)
    localStorage.setItem('edututor_user', JSON.stringify(u))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('edututor_token')
    localStorage.removeItem('edututor_user')
  }

  async function login(username: string, password: string) {
    const r = await client.post('/auth/login', { username, password })
    setAuth(r.data.token, r.data.user)
  }

  async function register(username: string, password: string) {
    const r = await client.post('/auth/register', { username, password })
    setAuth(r.data.token, r.data.user)
  }

  return { token, user, login, register, logout, setAuth }
})