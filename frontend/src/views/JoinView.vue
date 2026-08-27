<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { Workspace } from '../api/types'

// Reached via a shared invite link (/join/<token>). Requires login;
// the router guard redirects anonymous visitors to /login first.
const route = useRoute()

const joinedWorkspace = ref<Workspace | null>(null)
const error = ref('')
const pending = ref(true)

onMounted(async () => {
  const token = route.params.token as string
  try {
    joinedWorkspace.value = await api<Workspace>('/workspaces/join', {
      method: 'POST',
      body: { token },
    })
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to join workspace'
  } finally {
    pending.value = false
  }
})
</script>

<template>
  <main class="join">
    <h1>Workspace invite</h1>
    <p v-if="pending">Joining workspace…</p>
    <template v-else-if="joinedWorkspace">
      <p>
        You joined <strong>{{ joinedWorkspace.name }}</strong> as a member. 🌱
      </p>
      <router-link to="/">Go to your garden</router-link>
    </template>
    <template v-else>
      <p class="error">{{ error }}</p>
      <router-link to="/">Back to home</router-link>
    </template>
  </main>
</template>

<style scoped>
.join {
  max-width: 24rem;
  margin: 4rem auto;
  font-family: system-ui, sans-serif;
  text-align: center;
}

.error {
  color: #b00020;
}
</style>
