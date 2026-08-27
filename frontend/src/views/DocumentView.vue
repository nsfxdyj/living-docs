<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import type { Document, MergeRequest, TreeNode } from '../api/types'
import CountUp from '../components/CountUp.vue'
import { useReveal } from '../composables/useReveal'
import { badgeStyle } from '../utils/life'
import { renderMarkdown } from '../utils/markdown'

// Read-only rendered view of a single document.
const route = useRoute()
const router = useRouter()
const documentId = Number(route.params.id)

// Reveal-on-scroll root (document body fades in once loaded).
const root = ref<HTMLElement | null>(null)
useReveal(root)

const doc = ref<Document | null>(null)
const parentDoc = ref<Document | null>(null)
const error = ref('')
const loading = ref(true)
const forking = ref(false)
const proposing = ref(false)
const showMergePanel = ref(false)
const mergeTargets = ref<TreeNode[]>([])
const mergeTargetId = ref<number | null>(null)

const renderedHtml = computed(() =>
  doc.value === null ? '' : renderMarkdown(doc.value.content_md),
)

const isMerged = computed(() => doc.value?.status === 'merged')
const isFork = computed(() => doc.value !== null && doc.value.parent_id !== null)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

async function fork() {
  if (doc.value === null) return
  error.value = ''
  forking.value = true
  try {
    const created = await api<Document>(`/documents/${doc.value.id}/fork`, {
      method: 'POST',
    })
    router.push(`/docs/${created.id}/edit`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to fork document'
  } finally {
    forking.value = false
  }
}

async function openMergePanel() {
  if (doc.value === null) return
  error.value = ''
  // Candidate targets: the fork's ancestors, direct parent first.
  const tree = await api<TreeNode[]>(`/documents/${doc.value.id}/tree`)
  const byId = new Map(tree.map((node) => [node.id, node]))
  const ancestors: TreeNode[] = []
  let current = byId.get(doc.value.id)
  while (current !== undefined && current.parent_id !== null) {
    const parent = byId.get(current.parent_id)
    if (parent === undefined) break
    ancestors.push(parent)
    current = parent
  }
  mergeTargets.value = ancestors
  mergeTargetId.value = doc.value.parent_id
  showMergePanel.value = true
}

async function proposeMerge() {
  if (doc.value === null || mergeTargetId.value === null) return
  error.value = ''
  proposing.value = true
  try {
    const mr = await api<MergeRequest>(
      `/documents/${doc.value.id}/merge-requests`,
      { method: 'POST', body: { target_doc_id: mergeTargetId.value } },
    )
    router.push(`/merge/${mr.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to propose merge'
  } finally {
    proposing.value = false
  }
}

onMounted(async () => {
  try {
    doc.value = await api<Document>(`/documents/${documentId}`)
    if (doc.value.parent_id !== null) {
      // track=false: resolving the parent link is not a genuine view.
      parentDoc.value = await api<Document>(
        `/documents/${doc.value.parent_id}?track=false`,
      )
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load document'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main ref="root" class="doc-view">
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
            <span v-if="isMerged" class="badge merged-badge">merged ✓</span>
            <span class="badge" :style="badgeStyle(doc.status)">{{
              doc.status
            }}</span>
            <span class="vitality">
              ⚡ <CountUp :value="doc.vitality" /> vitality
            </span>
            <span v-for="tag in doc.tags" :key="tag" class="tag">#{{ tag }}</span>
            <span class="updated">
              last interaction {{ formatDate(doc.last_interaction_at) }}
            </span>
          </div>
          <p v-if="isFork && parentDoc" class="forked-from">
            Forked from
            <router-link :to="`/docs/${parentDoc.id}`">{{
              parentDoc.title
            }}</router-link>
          </p>
        </div>
        <div class="actions">
          <router-link :to="`/docs/${doc.id}/tree`" class="action-btn">
            Evolution tree
          </router-link>
          <button
            v-if="isFork && !isMerged"
            type="button"
            class="action-btn"
            @click="openMergePanel"
          >
            Propose merge
          </button>
          <button
            type="button"
            class="action-btn"
            :disabled="forking || isMerged"
            @click="fork"
          >
            {{ forking ? 'Forking…' : 'Fork' }}
          </button>
          <router-link :to="`/docs/${doc.id}/edit`" class="edit-btn">
            Edit
          </router-link>
        </div>
      </header>

      <div v-if="showMergePanel" class="merge-panel">
        <label>
          Merge into:
          <select v-model.number="mergeTargetId">
            <option
              v-for="target in mergeTargets"
              :key="target.id"
              :value="target.id"
            >
              {{ target.title }} (#{{ target.id }})
            </option>
          </select>
        </label>
        <button
          type="button"
          class="edit-btn"
          :disabled="proposing || mergeTargetId === null"
          @click="proposeMerge"
        >
          {{ proposing ? 'Proposing…' : 'Create merge request' }}
        </button>
        <button type="button" class="action-btn" @click="showMergePanel = false">
          Cancel
        </button>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <article class="content reveal" v-html="renderedHtml"></article>
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
  border: none;
  cursor: pointer;
}

.actions {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.action-btn {
  padding: 0.45rem 0.9rem;
  background: #fff;
  color: #2f8f4e;
  border: 1px solid #2f8f4e;
  border-radius: 6px;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  font-size: 1rem;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.forked-from {
  font-size: 0.85rem;
  color: #666;
  margin: 0.4rem 0 0;
}

.merged-badge {
  color: #4a4a4a;
  background: #dcdcdc;
}

.merge-panel {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid #d5e8dc;
  border-radius: 8px;
  background: #f4faf6;
}

.merge-panel select {
  padding: 0.35rem 0.5rem;
  margin-left: 0.4rem;
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
  /* Life-status changes cross-fade instead of snapping. */
  transition:
    color 500ms var(--ease-out),
    background-color 500ms var(--ease-out);
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
