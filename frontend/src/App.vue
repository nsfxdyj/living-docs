<script setup lang="ts">
import type { RouteLocationNormalizedLoaded } from 'vue-router'

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
</script>

<template>
  <router-view v-slot="{ Component, route }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="viewKey(route)" />
    </Transition>
  </router-view>
</template>
