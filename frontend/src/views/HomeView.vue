<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../api/client'
import type { Invite, Workspace, WorkspaceDetail } from '../api/types'
import { useReveal } from '../composables/useReveal'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

// Scroll-reveal root for the panels below.
const root = ref<HTMLElement | null>(null)
useReveal(root)

const workspaces = ref<Workspace[]>([])
const selected = ref<WorkspaceDetail | null>(null)
const newWorkspaceName = ref('')
const error = ref('')
const inviteLink = ref('')
const copied = ref(false)

async function loadWorkspaces() {
  workspaces.value = await api<Workspace[]>('/workspaces')
}

async function selectWorkspace(workspace: Workspace) {
  error.value = ''
  inviteLink.value = ''
  copied.value = false
  try {
    selected.value = await api<WorkspaceDetail>(`/workspaces/${workspace.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load workspace'
  }
}

async function createWorkspace() {
  error.value = ''
  try {
    const workspace = await api<Workspace>('/workspaces', {
      method: 'POST',
      body: { name: newWorkspaceName.value },
    })
    newWorkspaceName.value = ''
    await loadWorkspaces()
    await selectWorkspace(workspace)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to create workspace'
  }
}

async function generateInvite() {
  if (selected.value === null) return
  error.value = ''
  copied.value = false
  try {
    const invite = await api<Invite>(`/workspaces/${selected.value.id}/invites`, {
      method: 'POST',
    })
    // Absolute URL so the link can be shared outside this browser.
    inviteLink.value = `${window.location.origin}${invite.url}`
    await navigator.clipboard.writeText(inviteLink.value)
    copied.value = true
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to create invite'
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(async () => {
  try {
    if (auth.user === null) {
      await auth.fetchMe()
    }
    await loadWorkspaces()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load data'
  }
})
</script>

<template>
  <main ref="root" class="home">
    <header class="topbar">
      <h1>Living Docs Garden 🌱</h1>
      <div v-if="auth.user" class="account">
        <span>{{ auth.user.display_name }} ({{ auth.user.email }})</span>
        <button type="button" @click="logout">Log out</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <section class="panel reveal">
      <h2>My workspaces</h2>
      <ul v-if="workspaces.length" class="workspace-list">
        <li v-for="ws in workspaces" :key="ws.id">
          <button
            type="button"
            class="link"
            :class="{ active: selected?.id === ws.id }"
            @click="selectWorkspace(ws)"
          >
            {{ ws.name }}
          </button>
          <span class="role">{{ ws.role }}</span>
          <router-link :to="`/w/${ws.id}`" class="open">Open documents →</router-link>
        </li>
      </ul>
      <p v-else>You have not joined any workspace yet.</p>

      <form class="create" @submit.prevent="createWorkspace">
        <input
          v-model="newWorkspaceName"
          type="text"
          placeholder="New workspace name"
          required
        />
        <button type="submit">Create</button>
      </form>
    </section>

    <section v-if="selected" class="panel reveal" data-stagger="1">
      <h2>{{ selected.name }}</h2>
      <h3>Members</h3>
      <ul>
        <li v-for="member in selected.members" :key="member.user_id">
          {{ member.display_name }} ({{ member.email }}) — {{ member.role }}
        </li>
      </ul>
      <button
        v-if="selected.role === 'owner'"
        type="button"
        @click="generateInvite"
      >
        Generate invite link
      </button>
      <p v-if="inviteLink" class="invite">
        Invite link (valid 7 days): <code>{{ inviteLink }}</code>
        <span v-if="copied"> — copied to clipboard!</span>
      </p>
    </section>
  </main>
</template>

<style scoped>
.home {
  max-width: 44rem;
  margin: 2rem auto;
  padding: 0 1rem;
  font-family: system-ui, sans-serif;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.account {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.panel {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-top: 1.5rem;
}

.workspace-list button.link {
  background: none;
  border: none;
  padding: 0;
  color: #0645ad;
  cursor: pointer;
  font-size: 1rem;
  text-decoration: underline;
}

.workspace-list button.link.active {
  font-weight: bold;
}

.role {
  margin-left: 0.5rem;
  color: #777;
  font-size: 0.85rem;
}

.open {
  margin-left: 0.75rem;
  font-size: 0.85rem;
}

.create {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}

.create input {
  flex: 1;
  padding: 0.4rem 0.5rem;
  border: 1px solid #bbb;
  border-radius: 4px;
}

button {
  padding: 0.4rem 0.8rem;
  cursor: pointer;
}

/* Hover lift for real buttons (not the underline-styled .link buttons).
 * The shadow is pre-rendered on ::after and only its opacity is
 * transitioned — box-shadow itself is never animated. */
button:not(.link) {
  position: relative;
  transition: transform var(--dur-fast) var(--ease-spring);
}

button:not(.link)::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.14);
  opacity: 0;
  transition: opacity var(--dur-fast) var(--ease-out);
  pointer-events: none;
}

button:not(.link):hover:not(:disabled) {
  transform: translateY(-2px);
}

button:not(.link):hover:not(:disabled)::after {
  opacity: 1;
}

button:not(.link):active:not(:disabled) {
  transform: translateY(0);
}

.error {
  color: #b00020;
}

.invite code {
  word-break: break-all;
}
</style>
