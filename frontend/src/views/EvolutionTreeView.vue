<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import type { TreeNode } from '../api/types'
import { statusMeta } from '../utils/life'

// Evolution tree (M5): hand-drawn SVG. The root sits on the left, each
// generation one column to the right; node color = life status, node
// size scales with vitality, merged forks carry a ✓ mark.
const route = useRoute()
const router = useRouter()
const documentId = Number(route.params.id)

const nodes = ref<TreeNode[]>([])
const error = ref('')
const loading = ref(true)

const COLUMN_WIDTH = 200
const ROW_HEIGHT = 80
const PAD_X = 70
const PAD_Y = 50

interface Positioned {
  node: TreeNode
  depth: number
  x: number
  y: number
  radius: number
}

function nodeRadius(vitality: number): number {
  const capped = Math.min(Math.max(vitality, 0), 120)
  return 10 + (capped / 120) * 12 // 10px .. 22px
}

const positioned = computed<Positioned[]>(() => {
  const byId = new Map(nodes.value.map((node) => [node.id, node]))
  // Generation depth = distance from the root along parent links.
  const depthOf = (node: TreeNode): number => {
    let depth = 0
    let current: TreeNode | undefined = node
    const seen = new Set<number>()
    while (current !== undefined && current.parent_id !== null) {
      if (seen.has(current.id)) break
      seen.add(current.id)
      current = byId.get(current.parent_id)
      depth += 1
    }
    return depth
  }
  const layers = new Map<number, TreeNode[]>()
  for (const node of nodes.value) {
    const depth = depthOf(node)
    const layer = layers.get(depth) ?? []
    layer.push(node)
    layers.set(depth, layer)
  }
  const result: Positioned[] = []
  for (const [depth, layer] of layers) {
    layer.sort((a, b) => a.id - b.id)
    layer.forEach((node, index) => {
      result.push({
        node,
        depth,
        x: PAD_X + depth * COLUMN_WIDTH,
        y: PAD_Y + index * ROW_HEIGHT,
        radius: nodeRadius(node.vitality),
      })
    })
  }
  return result
})

const posById = computed(
  () => new Map(positioned.value.map((p) => [p.node.id, p])),
)

// Direct parent→child edges only (MVP scope per PLAN.md).
// `length` feeds the stroke-dashoffset draw-in animation.
const edges = computed(() =>
  positioned.value
    .filter((p) => p.node.parent_id !== null && posById.value.has(p.node.parent_id))
    .map((p) => {
      const parent = posById.value.get(p.node.parent_id as number) as Positioned
      return {
        from: parent,
        to: p,
        length: Math.hypot(p.x - parent.x, p.y - parent.y),
      }
    }),
)

const svgWidth = computed(() => {
  const maxDepth = Math.max(0, ...positioned.value.map((p) => p.depth))
  return PAD_X * 2 + maxDepth * COLUMN_WIDTH
})

const svgHeight = computed(() => {
  const maxY = Math.max(0, ...positioned.value.map((p) => p.y))
  return maxY + PAD_Y + 40
})

function nodeColor(node: TreeNode): string {
  if (node.merged) return '#8a8a8a'
  return statusMeta(node.status).leaf
}

function open(node: TreeNode) {
  router.push(`/docs/${node.id}`)
}

onMounted(async () => {
  try {
    nodes.value = await api<TreeNode[]>(`/documents/${documentId}/tree`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load tree'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="tree-view">
    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>
      <header class="topbar">
        <router-link :to="`/docs/${documentId}`" class="back">
          ← Back to document
        </router-link>
        <h1>Evolution tree</h1>
        <p class="hint">
          Node color = life status, size = vitality, ✓ = merged. Click a node
          to open the document.
        </p>
      </header>

      <div class="tree-scroll">
        <svg
          :width="svgWidth"
          :height="svgHeight"
          class="tree"
          role="img"
          aria-label="Document evolution tree"
        >
        <line
          v-for="(edge, i) in edges"
          :key="`${edge.from.node.id}->${edge.to.node.id}`"
          :x1="edge.from.x"
          :y1="edge.from.y"
          :x2="edge.to.x"
          :y2="edge.to.y"
          class="edge"
          :style="{
            '--len': `${edge.length}px`,
            animationDelay: `${i * 90}ms`,
          }"
        />
        <g
          v-for="(p, i) in positioned"
          :key="p.node.id"
          class="node"
          :style="{ animationDelay: `${150 + p.depth * 150 + i * 40}ms` }"
          @click="open(p.node)"
        >
          <title>
            {{ p.node.title }} — {{ p.node.author.display_name }} — ⚡{{
              Math.round(p.node.vitality)
            }}
            — {{ p.node.status }}{{ p.node.merged ? ' (merged)' : '' }}
          </title>
          <circle
            :cx="p.x"
            :cy="p.y"
            :r="p.radius"
            :fill="nodeColor(p.node)"
            :stroke="p.node.id === documentId ? '#111' : '#fff'"
            :stroke-width="p.node.id === documentId ? 3 : 2"
          />
          <text
            v-if="p.node.merged"
            :x="p.x"
            :y="p.y + 4"
            class="merged-mark"
          >
            ✓
          </text>
          <text :x="p.x" :y="p.y + p.radius + 14" class="label">
            {{
              p.node.title.length > 20
                ? p.node.title.slice(0, 20) + '…'
                : p.node.title
            }}
          </text>
        </g>
      </svg>
      </div>
    </template>
  </main>
</template>

<style scoped>
.tree-view {
  max-width: 64rem;
  margin: 2rem auto;
  padding: 0 1rem;
  font-family: system-ui, sans-serif;
}

.back {
  font-size: 0.9rem;
}

.hint {
  color: #666;
  font-size: 0.85rem;
}

.tree-scroll {
  margin-top: 1rem;
  overflow-x: auto;
  border: 1px solid #e2e2e2;
  border-radius: 8px;
}

.tree {
  display: block;
  background: #fcfcfc;
}

.edge {
  stroke: #b9b9b9;
  stroke-width: 2;
  /* Draw-in: the line is "painted" from parent to child on load. */
  stroke-dasharray: var(--len);
  stroke-dashoffset: var(--len);
  animation: edge-draw var(--dur-slow) var(--ease-out) forwards;
}

@keyframes edge-draw {
  to {
    stroke-dashoffset: 0;
  }
}

.node {
  cursor: pointer;
  /* Pop-in with a soft overshoot, staggered by generation depth. */
  transform-box: fill-box;
  transform-origin: center;
  animation: node-pop var(--dur-med) var(--ease-pop) both;
}

@keyframes node-pop {
  from {
    transform: scale(0);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}

.label {
  text-anchor: middle;
  font-size: 11px;
  fill: #444;
}

.merged-mark {
  text-anchor: middle;
  font-size: 12px;
  font-weight: bold;
  fill: #fff;
  pointer-events: none;
}

.error {
  color: #b00020;
}
</style>
