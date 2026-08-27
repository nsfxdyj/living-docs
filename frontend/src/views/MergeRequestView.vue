<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import type { Document, MergeRequest, WorkspaceDetail } from '../api/types'
import { useAuthStore } from '../stores/auth'

// Merge request page: unified diff of source vs target, plus accept/reject
// for the target author and the workspace owner.
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const mrId = Number(route.params.id)

const mr = ref<MergeRequest | null>(null)
const sourceDoc = ref<Document | null>(null)
const targetDoc = ref<Document | null>(null)
const workspace = ref<WorkspaceDetail | null>(null)
const diff = ref('')
const error = ref('')
const loading = ref(true)
const deciding = ref(false)

interface DiffLine {
  text: string
  kind: 'add' | 'del' | 'hunk' | 'meta' | 'context'
}

const diffLines = computed<DiffLine[]>(() =>
  diff.value.split('\n').map((line) => {
    let kind: DiffLine['kind'] = 'context'
    if (line.startsWith('+++') || line.startsWith('---')) kind = 'meta'
    else if (line.startsWith('@@')) kind = 'hunk'
    else if (line.startsWith('+')) kind = 'add'
    else if (line.startsWith('-')) kind = 'del'
    return { text: line, kind }
  }),
)

const canDecide = computed(() => {
  if (mr.value === null || targetDoc.value === null) return false
  if (mr.value.status !== 'open') return false
  const me = auth.user
  if (me === null) return false
  return (
    targetDoc.value.author_id === me.id || workspace.value?.role === 'owner'
  )
})

async function decide(action: 'accept' | 'reject') {
  if (mr.value === null) return
  error.value = ''
  deciding.value = true
  try {
    mr.value = await api<MergeRequest>(`/merge-requests/${mr.value.id}/${action}`, {
      method: 'POST',
    })
    if (action === 'accept') {
      router.push(`/docs/${mr.value.target_doc_id}`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : `Failed to ${action}`
  } finally {
    deciding.value = false
  }
}

onMounted(async () => {
  try {
    if (auth.user === null) {
      await auth.fetchMe()
    }
    mr.value = await api<MergeRequest>(`/merge-requests/${mrId}`)
    // track=false: opening this page is not a genuine "view" of either doc.
    const [source, target, diffText] = await Promise.all([
      api<Document>(`/documents/${mr.value.source_doc_id}?track=false`),
      api<Document>(`/documents/${mr.value.target_doc_id}?track=false`),
      // The diff endpoint returns plain text, so fetch it directly.
      fetch(`/api/merge-requests/${mrId}/diff`, {
        headers: { Authorization: `Bearer ${auth.token}` },
      }).then((res) => {
        if (!res.ok) throw new Error(`Failed to load diff (${res.status})`)
        return res.text()
      }),
    ])
    sourceDoc.value = source
    targetDoc.value = target
    diff.value = diffText
    workspace.value = await api<WorkspaceDetail>(
      `/workspaces/${target.workspace_id}`,
    )
  } catch (err) {
    error.value =
      err instanceof Error ? err.message : 'Failed to load merge request'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="mr-view">
    <p v-if="loading">Loading…</p>
    <p v-else-if="error && mr === null" class="error">{{ error }}</p>
    <template v-else-if="mr && sourceDoc && targetDoc">
      <header>
        <h1>Merge request #{{ mr.id }}</h1>
        <p class="summary">
          <router-link :to="`/docs/${sourceDoc.id}`">{{
            sourceDoc.title
          }}</router-link>
          →
          <router-link :to="`/docs/${targetDoc.id}`">{{
            targetDoc.title
          }}</router-link>
          <span class="status" :data-status="mr.status">{{ mr.status }}</span>
        </p>
        <div v-if="canDecide" class="decisions">
          <button
            type="button"
            class="accept"
            :disabled="deciding"
            @click="decide('accept')"
          >
            Accept
          </button>
          <button
            type="button"
            class="reject"
            :disabled="deciding"
            @click="decide('reject')"
          >
            Reject
          </button>
        </div>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <pre v-if="diffLines.length > 1" class="diff"><div
        v-for="(line, i) in diffLines"
        :key="i"
        class="diff-line"
        :class="line.kind"
      >{{ line.text }}</div></pre>
      <p v-else class="empty">No differences.</p>
    </template>
  </main>
</template>

<style scoped>
.mr-view {
  max-width: 56rem;
  margin: 2rem auto;
  padding: 0 1rem;
  font-family: system-ui, sans-serif;
}

.summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.status {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: #e4e4e4;
  color: #444;
}

.status[data-status='open'] {
  background: #fbf0d4;
  color: #8a6d1d;
}

.status[data-status='accepted'] {
  background: #d9f2e3;
  color: #1d6b3c;
}

.status[data-status='rejected'] {
  background: #f8d7da;
  color: #842029;
}

.decisions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.decisions button {
  padding: 0.45rem 0.9rem;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: #fff;
}

.accept {
  background: #2f8f4e;
}

.reject {
  background: #b02a37;
}

.diff {
  margin-top: 1.5rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.85rem;
  line-height: 1.45;
}

.diff-line {
  padding: 0 0.75rem;
  white-space: pre;
}

.diff-line.add {
  background: #e6ffec;
  color: #1a7f37;
}

.diff-line.del {
  background: #ffebe9;
  color: #cf222e;
}

.diff-line.hunk {
  background: #ddf4ff;
  color: #0969da;
}

.diff-line.meta {
  color: #666;
}

.error {
  color: #b00020;
}

.empty {
  color: #666;
}
</style>
