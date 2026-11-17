import { defineStore } from 'pinia'
import { auth as authApi } from '@/api'
import { getToken, setToken } from '@/api/http'

export const useAuth = defineStore('auth', {
  state: () => ({ token: getToken(), username: localStorage.getItem('iot_user') || '' }),
  getters: { loggedIn: (s) => !!s.token },
  actions: {
    async login(username, password) {
      const { token } = await authApi.login(username, password)
      this.token = token
      this.username = username
      setToken(token)
      localStorage.setItem('iot_user', username)
    },
    logout() {
      this.token = ''
      setToken('')
      localStorage.removeItem('iot_user')
    },
  },
})
