<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { Document, SearchResult, WorkspaceDetail } from '../api/types'
import { useReveal } from '../composables/useReveal'
import { badgeStyle } from '../utils/life'

// Workspace home: member list summary plus the searchable document list.
const route = useRoute()
const workspaceId = Number(route.params.id)

// Scroll-reveal root (document cards stagger in once fetched).
const root = ref<HTMLElement | null>(null)
useReveal(root)

const workspace = ref<WorkspaceDetail | null>(null)
const documents = ref<Document[]>([])
// null = browsing mode (document list); an array = full-text search results.
const searchResults = ref<SearchResult[] | null>(null)
const search = ref('')
const statusFilter = ref('')
const loading = ref(true)
const error = ref('')

const statusOptions = ['', 'thriving', 'stable', 'fading', 'withered']

async function loadDocuments() {
  error.value = ''
  const q = search.value.trim()
  try {
    if (q) {
      // Full-text search (title + content, FTS5). The status filter only
      // applies to browsing mode.
      searchResults.value = await api<SearchResult[]>(
        `/workspaces/${workspaceId}/search?${new URLSearchParams({ q })}`,
      )
      return
    }
    searchResults.value = null
    const params = new URLSearchParams({ parent: 'null' })
    if (statusFilter.value) params.set('status', statusFilter.value)
    documents.value = await api<Document[]>(
      `/workspaces/${workspaceId}/documents?${params}`,
    )
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load documents'
  }
}

// Turn a server snippet into safe HTML. The server marks matches with the
// control characters \u0001/\u0002 (never literal <b>) and strips those
// characters from indexed text, so document content cannot forge a
// highlight: escape everything first, then map the markers to <b>/<\/b>.
function snippetHtml(snippet: string): string {
  const OPEN = '\u0001'
  const CLOSE = '\u0002'
  const escaped = snippet
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  return escaped.split(OPEN).join('<b>').split(CLOSE).join('</b>')
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
  <main ref="root" class="workspace">
    <p v-if="loading">Loading…</p>
    <template v-else>
      <header class="topbar">
        <div>
          <router-link to="/" class="back">← All workspaces</router-link>
          <h1>{{ workspace?.name ?? 'Workspace' }}</h1>
        </div>
        <div class="actions">
          <router-link :to="`/w/${workspaceId}/garden`" class="garden-link">
            🌿 Garden
          </router-link>
          <router-link :to="`/w/${workspaceId}/docs/new`" class="new-doc">
            + New document
          </router-link>
        </div>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <form class="toolbar" @submit.prevent="loadDocuments">
        <input
          v-model="search"
          type="search"
          placeholder="Search titles and content…"
        />
        <select
          v-model="statusFilter"
          :disabled="search.trim() !== ''"
          title="Filter is available when browsing"
          @change="loadDocuments"
        >
          <option v-for="option in statusOptions" :key="option" :value="option">
            {{ option === '' ? 'All statuses' : option }}
          </option>
        </select>
        <button type="submit">Search</button>
      </form>

      <template v-if="searchResults !== null">
        <p v-if="!searchResults.length" class="empty">No matches found.</p>
        <ul v-else class="doc-list">
          <li
            v-for="(hit, i) in searchResults"
            :key="hit.id"
            class="doc-card reveal"
            :data-stagger="Math.min(i, 8)"
          >
            <router-link :to="`/docs/${hit.id}`" class="doc-title">
              {{ hit.title }}
            </router-link>
            <!-- eslint-disable-next-line vue/no-v-html -->
            <p class="doc-snippet" v-html="snippetHtml(hit.snippet)"></p>
            <div class="doc-meta">
              <span class="badge" :style="badgeStyle(hit.status)">{{
                hit.status
              }}</span>
              <span class="vitality">⚡ {{ Math.round(hit.vitality) }} vitality</span>
            </div>
          </li>
        </ul>
      </template>

      <template v-else>
        <p v-if="!documents.length" class="empty">
          No documents yet. Plant the first one! 🌱
        </p>

        <ul class="doc-list">
          <li
            v-for="(doc, i) in documents"
            :key="doc.id"
            class="doc-card reveal"
            :data-stagger="Math.min(i, 8)"
          >
            <router-link :to="`/docs/${doc.id}`" class="doc-title">
              {{ doc.title }}
            </router-link>
            <div class="doc-meta">
              <span class="badge" :style="badgeStyle(doc.status)">{{
                doc.status
              }}</span>
              <span class="vitality">⚡ {{ vitalityLabel(doc) }}</span>
              <span v-for="tag in doc.tags" :key="tag" class="tag">#{{ tag }}</span>
              <span class="updated">updated {{ formatDate(doc.last_interaction_at) }}</span>
            </div>
          </li>
        </ul>
      </template>
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

.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.garden-link {
  padding: 0.45rem 0.9rem;
  border: 1px solid #2f8f4e;
  color: #2f8f4e;
  border-radius: 6px;
  text-decoration: none;
  white-space: nowrap;
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

.doc-snippet {
  margin: 0.35rem 0 0;
  font-size: 0.9rem;
  color: #555;
}

.doc-snippet :deep(b) {
  color: #1d6f3c;
  background: #e2f3e8;
  border-radius: 3px;
  padding: 0 0.15em;
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
  /* Life-status changes cross-fade instead of snapping. */
  transition:
    color 500ms var(--ease-out),
    background-color 500ms var(--ease-out);
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
