<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { GardenEntry, Workspace } from '../api/types'
import {
  LIFE_STATUSES,
  lifeStatus,
  plantSize,
  statusMeta,
} from '../utils/life'

// The garden: every trunk document rendered as a plant whose size and
// color follow its vitality/status (M4).
const route = useRoute()
const workspaceId = Number(route.params.id)

const workspace = ref<Workspace | null>(null)
const entries = ref<GardenEntry[]>([])
const loading = ref(true)
const error = ref('')

const legend = LIFE_STATUSES.map((status) => ({ status, ...statusMeta(status) }))

const plants = computed(() =>
  entries.value.map((entry) => {
    const status = lifeStatus(entry.status)
    const meta = statusMeta(entry.status)
    return {
      entry,
      status,
      meta,
      size: plantSize(entry.vitality),
      tooltip: `${entry.title}\n⚡ ${Math.round(entry.vitality)} vitality — ${meta.label}\nLast interaction: ${new Date(
        entry.last_interaction_at,
      ).toLocaleString()}\nby ${entry.author.display_name}`,
    }
  }),
)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

onMounted(async () => {
  try {
    workspace.value = await api<Workspace>(`/workspaces/${workspaceId}`)
    entries.value = await api<GardenEntry[]>(`/workspaces/${workspaceId}/garden`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load garden'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="garden">
    <p v-if="loading">Loading…</p>
    <template v-else>
      <header class="topbar">
        <div>
          <router-link :to="`/w/${workspaceId}`" class="back">
            ← Document list
          </router-link>
          <h1>🌿 {{ workspace?.name ?? 'Workspace' }} Garden</h1>
        </div>
        <router-link :to="`/w/${workspaceId}/docs/new`" class="new-doc">
          + New document
        </router-link>
      </header>

      <p v-if="error" class="error">{{ error }}</p>

      <ul class="legend">
        <li v-for="item in legend" :key="item.status">
          <span
            class="badge"
            :style="{ color: item.color, background: item.background }"
            >{{ item.label }}</span
          >
        </li>
      </ul>

      <p v-if="!plants.length" class="empty">
        The garden is empty. Plant the first document! 🌱
      </p>

      <div class="bed">
        <router-link
          v-for="plant in plants"
          :key="plant.entry.id"
          :to="`/docs/${plant.entry.id}`"
          class="plant"
          :class="`plant-${plant.status}`"
          :title="plant.tooltip"
        >
          <svg
            :width="plant.size"
            :height="plant.size * 1.2"
            viewBox="0 0 100 120"
            role="img"
            :aria-label="`${plant.entry.title}: ${plant.meta.label}`"
          >
            <!-- ground -->
            <line
              x1="18"
              y1="110"
              x2="82"
              y2="110"
              stroke="#8b6f4e"
              stroke-width="6"
              stroke-linecap="round"
            />
            <!-- stem -->
            <line
              x1="50"
              y1="110"
              x2="50"
              y2="48"
              :stroke="plant.meta.stem"
              stroke-width="5"
              stroke-linecap="round"
            />
            <!-- leaves -->
            <ellipse
              cx="33"
              cy="76"
              rx="13"
              ry="7"
              :fill="plant.meta.leaf"
              transform="rotate(-30 33 76)"
            />
            <ellipse
              cx="67"
              cy="76"
              rx="13"
              ry="7"
              :fill="plant.meta.leaf"
              transform="rotate(30 67 76)"
            />
            <!-- canopy -->
            <ellipse cx="50" cy="36" rx="26" ry="24" :fill="plant.meta.leaf" />
          </svg>
          <span class="plant-title">{{ plant.entry.title }}</span>
          <span
            class="badge"
            :style="{ color: plant.meta.color, background: plant.meta.background }"
            >{{ plant.meta.label }}</span
          >
          <span class="plant-vitality">⚡ {{ Math.round(plant.entry.vitality) }}</span>
          <span class="plant-updated">
            {{ formatDate(plant.entry.last_interaction_at) }}
          </span>
        </router-link>
      </div>
    </template>
  </main>
</template>

<style scoped>
.garden {
  max-width: 64rem;
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

.legend {
  list-style: none;
  display: flex;
  gap: 0.5rem;
  padding: 0;
  margin: 1rem 0;
  flex-wrap: wrap;
}

.badge {
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.bed {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
  gap: 1rem;
  align-items: end;
  padding: 1rem;
  border: 1px solid #ddd;
  border-radius: 10px;
  background: linear-gradient(#f4faf2, #eef5ec);
}

.plant {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem;
  border-radius: 8px;
  text-decoration: none;
  color: inherit;
  text-align: center;
}

.plant:hover {
  background: rgba(47, 143, 78, 0.08);
}

.plant svg {
  transition: transform 0.15s ease;
}

.plant:hover svg {
  transform: scale(1.06);
}

/* Withered plants droop and fade. */
.plant-withered svg {
  transform: rotate(10deg);
  opacity: 0.65;
  filter: grayscale(0.6);
}

.plant-withered:hover svg {
  transform: rotate(10deg) scale(1.06);
}

.plant-title {
  font-weight: 600;
  font-size: 0.9rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.plant-vitality {
  font-size: 0.8rem;
  color: #666;
}

.plant-updated {
  font-size: 0.7rem;
  color: #999;
}

.empty,
.error {
  margin-top: 1rem;
}

.error {
  color: #b00020;
}
</style>
