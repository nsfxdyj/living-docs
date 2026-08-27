import { defineStore } from 'pinia'

import { api, getToken } from '../api/client'
import type { AppNotification } from '../api/types'

// Notifications (M6): the REST list is the source of truth; an EventSource
// stream prepends live events. The stream authenticates via ?token= because
// EventSource cannot set headers. connect() on login, disconnect() on logout.
export const useNotificationStore = defineStore('notifications', {
  state: () => ({
    items: [] as AppNotification[],
    eventSource: null as EventSource | null,
    // Bumped on every live event so the bell badge can pulse once.
    liveCounter: 0,
  }),
  getters: {
    unreadCount: (state) => state.items.filter((n) => !n.read).length,
  },
  actions: {
    connect() {
      if (this.eventSource !== null) return
      const token = getToken()
      if (token === null) return
      const stream = new EventSource(
        `/api/notifications/stream?token=${encodeURIComponent(token)}`,
      )
      stream.addEventListener('notification', (event) => {
        const notification = JSON.parse(
          (event as MessageEvent).data,
        ) as AppNotification
        this.items = [
          notification,
          ...this.items.filter((n) => n.id !== notification.id),
        ].slice(0, 50)
        this.liveCounter += 1
      })
      this.eventSource = stream
      void this.fetchAll()
    },
    disconnect() {
      this.eventSource?.close()
      this.eventSource = null
      this.items = []
    },
    async fetchAll() {
      this.items = await api<AppNotification[]>('/notifications')
    },
    async markRead(id: number) {
      await api(`/notifications/${id}/read`, { method: 'POST' })
      const item = this.items.find((n) => n.id === id)
      if (item !== undefined) item.read = true
    },
    async markAllRead() {
      await api('/notifications/read-all', { method: 'POST' })
      for (const item of this.items) item.read = true
    },
  },
})
