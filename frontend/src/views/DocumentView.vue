<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import type {
  DocComment,
  Document,
  Member,
  MergeRequest,
  TreeNode,
  WorkspaceDetail,
} from '../api/types'
import CountUp from '../components/CountUp.vue'
import { useReveal } from '../composables/useReveal'
import { useAuthStore } from '../stores/auth'
import { badgeStyle } from '../utils/life'
import { renderMarkdown } from '../utils/markdown'

// Read-only rendered view of a single document.
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
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

// M6 comments: list, composer and delete permissions (author or workspace
// owner — the role comes from the workspace detail).
const comments = ref<DocComment[]>([])
const newComment = ref('')
const submittingComment = ref(false)
const myRole = ref<string | null>(null)
// Workspace members, used to highlight @mentions in comment bodies.
const members = ref<Member[]>([])

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
    const [commentList, workspace] = await Promise.all([
      api<DocComment[]>(`/documents/${documentId}/comments`),
      api<WorkspaceDetail>(`/workspaces/${doc.value.workspace_id}`),
    ])
    comments.value = commentList
    myRole.value = workspace.role
    members.value = workspace.members
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load document'
  } finally {
    loading.value = false
  }
})

function canDeleteComment(comment: DocComment): boolean {
  return auth.user?.id === comment.author.id || myRole.value === 'owner'
}

// Split a comment body into plain-text and @mention segments. Rendered as
// DOM fragments (never v-html), so mention highlighting is XSS-safe.
// Matches the backend rule: exact display_name, trailing non-word boundary.
interface BodySegment {
  text: string
  mention: boolean
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function bodySegments(body: string): BodySegment[] {
  const names = members.value
    .map((m) => m.display_name)
    .filter((name) => name.length > 0)
    .sort((a, b) => b.length - a.length)
  if (names.length === 0) return [{ text: body, mention: false }]
  // Unicode-aware boundaries matching the backend's \w (letters/numbers/_
  // in any script): a leading letter/digit/@ (e.g. an email address) or a
  // trailing word character prevents a match.
  const pattern = new RegExp(
    `(?<![\\p{L}\\p{N}_@])@(?:${names.map(escapeRegExp).join('|')})(?![\\p{L}\\p{N}_])`,
    'gu',
  )
  const segments: BodySegment[] = []
  let last = 0
  for (const match of body.matchAll(pattern)) {
    const start = match.index
    if (start > last) segments.push({ text: body.slice(last, start), mention: false })
    segments.push({ text: match[0], mention: true })
    last = start + match[0].length
  }
  if (last < body.length) segments.push({ text: body.slice(last), mention: false })
  return segments
}

async function submitComment() {
  if (doc.value === null || newComment.value.trim() === '') return
  error.value = ''
  submittingComment.value = true
  try {
    const created = await api<DocComment>(`/documents/${doc.value.id}/comments`, {
      method: 'POST',
      body: { body: newComment.value.trim() },
    })
    comments.value.push(created)
    newComment.value = ''
    // The comment charged the document (+5): refresh vitality/status without
    // recording another view.
    doc.value = await api<Document>(`/documents/${doc.value.id}?track=false`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to post comment'
  } finally {
    submittingComment.value = false
  }
}

async function deleteComment(comment: DocComment) {
  error.value = ''
  try {
    await api(`/comments/${comment.id}`, { method: 'DELETE' })
    comments.value = comments.value.filter((c) => c.id !== comment.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to delete comment'
  }
}
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

      <section class="comments reveal" data-stagger="1">
        <h2>Comments ({{ comments.length }})</h2>
        <p v-if="comments.length === 0" class="no-comments">
          No comments yet — say something to charge this document (+5 vitality).
        </p>
        <ul v-else class="comment-list">
          <li v-for="comment in comments" :key="comment.id" class="comment">
            <div class="comment-head">
              <span class="comment-author">{{ comment.author.display_name }}</span>
              <span class="comment-time">{{ formatDate(comment.created_at) }}</span>
              <button
                v-if="canDeleteComment(comment)"
                type="button"
                class="comment-delete"
                @click="deleteComment(comment)"
              >
                Delete
              </button>
            </div>
            <p class="comment-body">
              <template
                v-for="(segment, i) in bodySegments(comment.body)"
                :key="i"
              ><span v-if="segment.mention" class="mention">{{ segment.text }}</span
              ><template v-else>{{ segment.text }}</template></template>
            </p>
          </li>
        </ul>
        <form class="comment-form" @submit.prevent="submitComment">
          <textarea
            v-model="newComment"
            rows="3"
            maxlength="2000"
            placeholder="Write a comment…"
            required
          ></textarea>
          <button type="submit" class="edit-btn" :disabled="submittingComment">
            {{ submittingComment ? 'Posting…' : 'Post comment' }}
          </button>
        </form>
      </section>
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

.comments {
  margin-top: 2.5rem;
  border-top: 1px solid #e2e2e2;
  padding-top: 1.25rem;
}

.comments h2 {
  font-size: 1.1rem;
  margin: 0 0 0.75rem;
}

.no-comments {
  color: #777;
  font-size: 0.9rem;
}

.comment-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.comment {
  border: 1px solid #e2e2e2;
  border-radius: 8px;
  padding: 0.6rem 0.9rem;
}

.comment-head {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
}

.comment-author {
  font-weight: 600;
  font-size: 0.9rem;
}

.comment-time {
  color: #999;
  font-size: 0.78rem;
}

.comment-delete {
  margin-left: auto;
  border: none;
  background: none;
  color: #b00020;
  cursor: pointer;
  font-size: 0.78rem;
  padding: 0;
}

.comment-body {
  margin: 0.35rem 0 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.mention {
  padding: 0 0.35em;
  border-radius: 999px;
  background: #e2f3e8;
  color: #1d6f3c;
  font-weight: 600;
}

.comment-form {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin-top: 1rem;
}

.comment-form textarea {
  padding: 0.5rem 0.6rem;
  border: 1px solid #bbb;
  border-radius: 6px;
  font: inherit;
  resize: vertical;
}

.comment-form .edit-btn {
  align-self: flex-end;
}
</style>
