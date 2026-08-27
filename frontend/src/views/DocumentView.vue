<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { Document } from '../api/types'
import { renderMarkdown } from '../utils/markdown'

// Read-only rendered view of a single document.
const route = useRoute()
const documentId = Number(route.params.id)

const doc = ref<Document | null>(null)
const error = ref('')
const loading = ref(true)

const renderedHtml = computed(() =>
  doc.value === null ? '' : renderMarkdown(doc.value.content_md),
)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

onMounted(async () => {
  try {
    doc.value = await api<Document>(`/documents/${documentId}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load document'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="doc-view">
    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else-if="doc">
      <header class="topbar">
        <div>
          <router-link :to="`/w/${doc.workspace_id}`" class="back">
            ← Back to workspace
          </router-link>
          <h1>{{ doc.title }}</h1>
          <div class="meta">
            <span class="badge" :class="`status-${doc.status}`">{{
              doc.status
            }}</span>
            <span class="vitality">⚡ {{ Math.round(doc.vitality) }} vitality</span>
            <span v-for="tag in doc.tags" :key="tag" class="tag">#{{ tag }}</span>
            <span class="updated">
              last interaction {{ formatDate(doc.last_interaction_at) }}
            </span>
          </div>
        </div>
        <router-link :to="`/docs/${doc.id}/edit`" class="edit-btn">
          Edit
        </router-link>
      </header>

      <article class="content" v-html="renderedHtml"></article>
    </template>
  </main>
</template>

<style scoped>
.doc-view {
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
}

.back {
  font-size: 0.9rem;
}

.edit-btn {
  padding: 0.45rem 0.9rem;
  background: #2f8f4e;
  color: #fff;
  border-radius: 6px;
  text-decoration: none;
  white-space: nowrap;
}

.meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
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

.content {
  margin-top: 1.5rem;
  line-height: 1.6;
}

.content :deep(pre) {
  background: #f6f8fa;
  padding: 0.75rem;
  border-radius: 6px;
  overflow-x: auto;
}

.content :deep(img) {
  max-width: 100%;
}

.error {
  color: #b00020;
}
</style>
