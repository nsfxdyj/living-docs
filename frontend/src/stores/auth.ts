import { defineStore } from 'pinia'

import { api, getToken, setToken } from '../api/client'
import type { AuthResponse, User } from '../api/types'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getToken() as string | null,
    user: null as User | null,
  }),
  getters: {
    isAuthenticated: (state) => state.token !== null,
  },
  actions: {
    _applyAuth(response: AuthResponse) {
      setToken(response.token)
      this.token = response.token
      this.user = response.user
    },
    async login(email: string, password: string) {
      const response = await api<AuthResponse>('/auth/login', {
        method: 'POST',
        body: { email, password },
      })
      this._applyAuth(response)
    },
    async register(email: string, password: string, displayName: string) {
      const response = await api<AuthResponse>('/auth/register', {
        method: 'POST',
        body: { email, password, display_name: displayName },
      })
      this._applyAuth(response)
    },
    async fetchMe() {
      this.user = await api<User>('/auth/me')
    },
    logout() {
      setToken(null)
      this.token = null
      this.user = null
    },
  },
})
