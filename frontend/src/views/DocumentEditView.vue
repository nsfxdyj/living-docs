<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, apiUpload } from '../api/client'
import type { AttachmentUpload, Document } from '../api/types'
import { renderMarkdown } from '../utils/markdown'

// Split-pane Markdown editor. Handles both creating a document inside a
// workspace (/w/:id/docs/new) and editing an existing one (/docs/:id/edit).
// Computed from the route because uploading an image on a fresh document
// saves it first and swaps the route to /docs/:id/edit in place.
const route = useRoute()
const router = useRouter()

const isNew = computed(() => route.name === 'doc-new')
const workspaceId = Number(route.params.id)
const documentId = computed(() =>
  isNew.value ? null : Number(route.params.id),
)

const title = ref('')
const content = ref('')
const tagsInput = ref('')
const loading = ref(route.name === 'doc-new' ? false : true)
const saving = ref(false)
const uploading = ref(false)
const error = ref('')

const editor = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

const previewHtml = computed(() => renderMarkdown(content.value))

function parseTags(): string[] {
  return tagsInput.value
    .split(',')
    .map((tag) => tag.trim())
    .filter((tag) => tag.length > 0)
}

async function save() {
  error.value = ''
  saving.value = true
  try {
    const payload = {
      title: title.value,
      content_md: content.value,
      tags: parseTags(),
    }
    if (isNew.value) {
      const created = await api<Document>(
        `/workspaces/${workspaceId}/documents`,
        { method: 'POST', body: payload },
      )
      router.replace(`/docs/${created.id}`)
    } else {
      const updated = await api<Document>(`/documents/${documentId.value}`, {
        method: 'PATCH',
        body: payload,
      })
      router.push(`/docs/${updated.id}`)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to save document'
  } finally {
    saving.value = false
  }
}

function insertAtCursor(snippet: string) {
  const textarea = editor.value
  if (textarea === null) {
    content.value += snippet
    return
  }
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  content.value =
    content.value.slice(0, start) + snippet + content.value.slice(end)
  // Restore the cursor right after the inserted snippet.
  requestAnimationFrame(() => {
    textarea.focus()
    textarea.selectionStart = textarea.selectionEnd = start + snippet.length
  })
}

async function uploadImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  // For a brand-new document we can upload only after it exists, so save first.
  error.value = ''
  uploading.value = true
  try {
    let targetId = documentId.value
    if (isNew.value) {
      const created = await api<Document>(
        `/workspaces/${workspaceId}/documents`,
        {
          method: 'POST',
          body: {
            title: title.value || 'Untitled',
            content_md: content.value,
            tags: parseTags(),
          },
        },
      )
      targetId = created.id
      router.replace({ name: 'doc-edit', params: { id: created.id } })
    }
    const attachment = await apiUpload<AttachmentUpload>(
      `/documents/${targetId}/attachments`,
      file,
    )
    insertAtCursor(`\n![${file.name}](${attachment.url})\n`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to upload image'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

function cancel() {
  if (isNew.value) {
    router.push(`/w/${workspaceId}`)
  } else {
    router.push(`/docs/${documentId.value}`)
  }
}

onMounted(async () => {
  if (isNew.value) return
  try {
    const doc = await api<Document>(`/documents/${documentId.value}`)
    title.value = doc.title
    content.value = doc.content_md
    tagsInput.value = doc.tags.join(', ')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load document'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="editor-page">
    <p v-if="loading">Loading…</p>
    <template v-else>
      <header class="toolbar">
        <input
          v-model="title"
          type="text"
          class="title-input"
          placeholder="Document title"
          required
        />
        <input
          v-model="tagsInput"
          type="text"
          class="tags-input"
          placeholder="tags, comma separated"
        />
        <button type="button" :disabled="uploading" @click="fileInput?.click()">
          {{ uploading ? 'Uploading…' : 'Upload image' }}
        </button>
        <input
          ref="fileInput"
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp"
          hidden
          @change="uploadImage"
        />
        <button type="button" class="primary" :disabled="saving" @click="save">
          {{ saving ? 'Saving…' : 'Save' }}
        </button>
        <button type="button" @click="cancel">Cancel</button>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <div class="split">
        <textarea
          ref="editor"
          v-model="content"
          class="pane editor"
          placeholder="Write Markdown here…"
        ></textarea>
        <div class="pane preview" v-html="previewHtml"></div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.editor-page {
  max-width: 72rem;
  margin: 1.5rem auto;
  padding: 0 1rem;
  font-family: system-ui, sans-serif;
}

.toolbar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}

.title-input {
  flex: 2;
  min-width: 12rem;
  padding: 0.45rem 0.6rem;
  font-size: 1.05rem;
  border: 1px solid #bbb;
  border-radius: 4px;
}

.tags-input {
  flex: 1;
  min-width: 8rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid #bbb;
  border-radius: 4px;
}

button {
  padding: 0.45rem 0.9rem;
  cursor: pointer;
}

button.primary {
  background: #2f8f4e;
  color: #fff;
  border: none;
  border-radius: 6px;
}

.split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-top: 1rem;
  height: 70vh;
}

.pane {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  overflow: auto;
}

.editor {
  resize: none;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.95rem;
  line-height: 1.5;
}

.preview :deep(pre) {
  background: #f6f8fa;
  padding: 0.75rem;
  border-radius: 6px;
  overflow-x: auto;
}

.preview :deep(img) {
  max-width: 100%;
}

@media (max-width: 720px) {
  .split {
    grid-template-columns: 1fr;
    height: auto;
  }

  .pane {
    min-height: 16rem;
  }
}

.error {
  color: #b00020;
}
</style>
