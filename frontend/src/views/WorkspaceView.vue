<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { Document, WorkspaceDetail } from '../api/types'

// Workspace home: member list summary plus the searchable document list.
const route = useRoute()
const workspaceId = Number(route.params.id)

const workspace = ref<WorkspaceDetail | null>(null)
const documents = ref<Document[]>([])
const search = ref('')
const statusFilter = ref('')
const loading = ref(true)
const error = ref('')

const statusOptions = ['', 'thriving', 'stable', 'fading', 'withered']

async function loadDocuments() {
  error.value = ''
  const params = new URLSearchParams({ parent: 'null' })
  if (search.value.trim()) params.set('q', search.value.trim())
  if (statusFilter.value) params.set('status', statusFilter.value)
  try {
    documents.value = await api<Document[]>(
      `/workspaces/${workspaceId}/documents?${params}`,
    )
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load documents'
  }
}

onMounted(async () => {
  try {
    workspace.value = await api<WorkspaceDetail>(`/workspaces/${workspaceId}`)
    await loadDocuments()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load workspace'
  } finally {
    loading.value = false
  }
})

const vitalityLabel = computed(() => (doc: Document) =>
  `${Math.round(doc.vitality)} vitality`,
)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}
</script>

<template>
  <main class="workspace">
    <p v-if="loading">Loading…</p>
    <template v-else>
      <header class="topbar">
        <div>
          <router-link to="/" class="back">← All workspaces</router-link>
          <h1>{{ workspace?.name ?? 'Workspace' }}</h1>
        </div>
        <router-link :to="`/w/${workspaceId}/docs/new`" class="new-doc">
          + New document
        </router-link>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <form class="toolbar" @submit.prevent="loadDocuments">
        <input
          v-model="search"
          type="search"
          placeholder="Search documents by title…"
        />
        <select v-model="statusFilter" @change="loadDocuments">
          <option v-for="option in statusOptions" :key="option" :value="option">
            {{ option === '' ? 'All statuses' : option }}
          </option>
        </select>
        <button type="submit">Search</button>
      </form>

      <p v-if="!documents.length" class="empty">
        No documents yet. Plant the first one! 🌱
      </p>

      <ul class="doc-list">
        <li v-for="doc in documents" :key="doc.id" class="doc-card">
          <router-link :to="`/docs/${doc.id}`" class="doc-title">
            {{ doc.title }}
          </router-link>
          <div class="doc-meta">
            <span class="badge" :class="`status-${doc.status}`">{{
              doc.status
            }}</span>
            <span class="vitality">⚡ {{ vitalityLabel(doc) }}</span>
            <span v-for="tag in doc.tags" :key="tag" class="tag">#{{ tag }}</span>
            <span class="updated">updated {{ formatDate(doc.last_interaction_at) }}</span>
          </div>
        </li>
      </ul>
    </template>
  </main>
</template>

<style scoped>
.workspace {
  max-width: 52rem;
  margin: 2rem auto;
  padding: 0 1rem;
  font-family: system-ui, sans-serif;
}

.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.back {
  font-size: 0.9rem;
}

.new-doc {
  padding: 0.45rem 0.9rem;
  background: #2f8f4e;
  color: #fff;
  border-radius: 6px;
  text-decoration: none;
  white-space: nowrap;
}

.toolbar {
  display: flex;
  gap: 0.5rem;
  margin: 1rem 0;
  flex-wrap: wrap;
}

.toolbar input {
  flex: 1;
  min-width: 12rem;
  padding: 0.4rem 0.5rem;
  border: 1px solid #bbb;
  border-radius: 4px;
}

.toolbar select {
  padding: 0.4rem;
  border: 1px solid #bbb;
  border-radius: 4px;
}

.doc-list {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.75rem;
}

.doc-card {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 0.75rem 1rem;
}

.doc-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: #0645ad;
  text-decoration: none;
}

.doc-title:hover {
  text-decoration: underline;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 0.4rem;
  font-size: 0.85rem;
  color: #666;
}

.badge {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.status-thriving {
  background: #d9f2e3;
  color: #1d6b3c;
}

.status-stable {
  background: #e3ecfb;
  color: #2c5aa0;
}

.status-fading {
  background: #fbf0d4;
  color: #8a6d1d;
}

.status-withered {
  background: #e4e4e4;
  color: #666;
}

.tag {
  color: #777;
}

.empty,
.error {
  margin-top: 1rem;
}

.error {
  color: #b00020;
}
</style>
