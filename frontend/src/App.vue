<script setup lang="ts">
import { onMounted, watch } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

import NotificationBell from './components/NotificationBell.vue'
import { useAuthStore } from './stores/auth'
import { useNotificationStore } from './stores/notifications'

// key=fullPath: same-component param navigation (e.g. /docs/1 -> /docs/2)
// remounts the view, replaying the transition and the view's onMounted
// data fetch.
//
// Exception: the markdown editor intentionally swaps /w/:id/docs/new to
// /docs/:id/edit *in place* after the first save/image upload (see
// DocumentEditView) and keeps mutating its unsaved buffer afterwards —
// remounting there would wipe that buffer, so the editor keeps a stable
// key. (Param-only navigation between two edit pages is not refetched,
// which matches the pre-transition behavior of having no key at all.)
function viewKey(route: RouteLocationNormalizedLoaded): string {
  if (route.name === 'doc-new' || route.name === 'doc-edit') return 'doc-editor'
  return route.fullPath
}

// M6: the notification stream lives at app level — connected while
// authenticated (including across reloads via the stored token), closed
// on logout.
const auth = useAuthStore()
const notifications = useNotificationStore()

watch(
  () => auth.isAuthenticated,
  (loggedIn) => {
    if (loggedIn) {
      notifications.connect()
    } else {
      notifications.disconnect()
    }
  },
)

onMounted(() => {
  if (auth.isAuthenticated) notifications.connect()
})
</script>

<template>
  <NotificationBell v-if="auth.isAuthenticated" />
  <router-view v-slot="{ Component, route }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="viewKey(route)" />
    </Transition>
  </router-view>
</template>
