<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { AppNotification } from '../api/types'
import { useNotificationStore } from '../stores/notifications'

// Global notification bell (M6): fixed in the top-right corner, shows the
// unread count and a dropdown with the most recent notifications.
const notifications = useNotificationStore()
const router = useRouter()

const open = ref(false)
const pulsing = ref(false)

// Pulse the badge once whenever a live SSE event arrives.
watch(
  () => notifications.liveCounter,
  (value) => {
    if (value === 0) return
    pulsing.value = false
    requestAnimationFrame(() => {
      pulsing.value = true
    })
  },
)

function describe(notification: AppNotification): string {
  const p = notification.payload
  const actor = p.actor_name ?? 'Someone'
  switch (notification.kind) {
    case 'comment':
      return `${actor} commented on “${p.document_title ?? 'a document'}”`
    case 'mention':
      return `${actor} mentioned you in “${p.document_title ?? 'a document'}”`
    case 'merge_request':
      return `${actor} requested to merge “${p.source_title ?? ''}” into “${p.target_title ?? ''}”`
    case 'merge_accepted':
      return `${actor} accepted your merge into “${p.target_title ?? ''}”`
    case 'merge_rejected':
      return `${actor} rejected your merge into “${p.target_title ?? ''}”`
    default:
      return 'New activity'
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

async function openNotification(notification: AppNotification) {
  open.value = false
  if (!notification.read) {
    try {
      await notifications.markRead(notification.id)
    } catch {
      // Non-fatal: navigation still proceeds.
    }
  }
  if (
    (notification.kind === 'comment' || notification.kind === 'mention') &&
    notification.payload.document_id
  ) {
    router.push(`/docs/${notification.payload.document_id}`)
  } else if (notification.payload.merge_request_id) {
    router.push(`/merge/${notification.payload.merge_request_id}`)
  }
}

async function markAllRead() {
  try {
    await notifications.markAllRead()
  } catch {
    // Non-fatal: the next fetch resyncs the list.
  }
}
</script>

<template>
  <div class="bell-root">
    <button
      type="button"
      class="bell-btn"
      :class="{ active: open }"
      aria-label="Notifications"
      @click="open = !open"
    >
      🔔
      <span
        v-if="notifications.unreadCount > 0"
        class="badge"
        :class="{ pulse: pulsing }"
        @animationend="pulsing = false"
        >{{ notifications.unreadCount > 99 ? '99+' : notifications.unreadCount }}</span
      >
    </button>

    <Transition name="panel">
      <div v-if="open" class="panel">
        <div class="panel-head">
          <span>Notifications</span>
          <button
            v-if="notifications.unreadCount > 0"
            type="button"
            class="read-all"
            @click="markAllRead"
          >
            Mark all read
          </button>
        </div>
        <p v-if="notifications.items.length === 0" class="empty">
          No notifications yet.
        </p>
        <ul v-else class="items">
          <li v-for="n in notifications.items" :key="n.id">
            <button
              type="button"
              class="item"
              :class="{ unread: !n.read }"
              @click="openNotification(n)"
            >
              <span class="text">{{ describe(n) }}</span>
              <span class="time">{{ formatTime(n.created_at) }}</span>
            </button>
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.bell-root {
  position: fixed;
  top: 0.75rem;
  right: 0.75rem;
  z-index: 100;
  font-family: system-ui, sans-serif;
}

.bell-btn {
  position: relative;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  border: 1px solid #ddd;
  background: #fff;
  cursor: pointer;
  font-size: 1.1rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: transform var(--dur-fast) var(--ease-spring);
}

.bell-btn:hover {
  transform: translateY(-2px);
}

.bell-btn.active {
  border-color: #2f8f4e;
}

.badge {
  position: absolute;
  top: -0.3rem;
  right: -0.3rem;
  min-width: 1.2rem;
  height: 1.2rem;
  padding: 0 0.25rem;
  border-radius: 999px;
  background: #c0392b;
  color: #fff;
  font-size: 0.7rem;
  line-height: 1.2rem;
  text-align: center;
}

/* One-shot pulse when a live notification arrives. */
.badge.pulse {
  animation: badge-pulse 600ms var(--ease-pop);
}

@keyframes badge-pulse {
  0% {
    transform: scale(1);
  }
  40% {
    transform: scale(1.35);
  }
  100% {
    transform: scale(1);
  }
}

/* Dropdown: fade + slight slide down. */
.panel-enter-active {
  transition:
    opacity var(--dur-fast) var(--ease-spring),
    transform var(--dur-fast) var(--ease-spring);
}

.panel-leave-active {
  transition:
    opacity var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-out);
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.panel {
  position: absolute;
  top: 3rem;
  right: 0;
  width: 20rem;
  max-height: 24rem;
  overflow-y: auto;
  border: 1px solid #ddd;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.14);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 0.9rem;
  border-bottom: 1px solid #eee;
  font-weight: 600;
  font-size: 0.9rem;
}

.read-all {
  border: none;
  background: none;
  color: #2f8f4e;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 0;
}

.empty {
  padding: 1rem 0.9rem;
  margin: 0;
  color: #777;
  font-size: 0.85rem;
}

.items {
  list-style: none;
  margin: 0;
  padding: 0;
}

.item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  width: 100%;
  padding: 0.6rem 0.9rem;
  border: none;
  border-bottom: 1px solid #f2f2f2;
  background: none;
  text-align: left;
  cursor: pointer;
  font-size: 0.85rem;
}

.item:hover {
  background: #f6faf7;
}

.item.unread .text {
  font-weight: 600;
}

.item.unread .text::before {
  content: '● ';
  color: #2f8f4e;
}

.time {
  color: #999;
  font-size: 0.75rem;
}
</style>
