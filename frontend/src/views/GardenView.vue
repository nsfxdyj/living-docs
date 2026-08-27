<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { api } from '../api/client'
import type { GardenEntry, Workspace } from '../api/types'
import CountUp from '../components/CountUp.vue'
import { useReveal } from '../composables/useReveal'
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

// Reveal-on-scroll root (plants grow in with a stagger once fetched).
const root = ref<HTMLElement | null>(null)
useReveal(root)

const legend = LIFE_STATUSES.map((status) => ({ status, ...statusMeta(status) }))

const plants = computed(() =>
  entries.value.map((entry) => {
    const status = lifeStatus(entry.status)
    const meta = statusMeta(entry.status)
    return { entry, status, meta, size: plantSize(entry.vitality) }
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
  <main ref="root" class="garden">
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
        <li
          v-for="(item, i) in legend"
          :key="item.status"
          class="reveal"
          :data-stagger="i"
        >
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
          v-for="(plant, i) in plants"
          :key="plant.entry.id"
          :to="`/docs/${plant.entry.id}`"
          class="plant reveal"
          :class="`plant-${plant.status}`"
          :data-stagger="Math.min(i, 10)"
          :style="{ '--i': i }"
          :aria-describedby="`plant-tip-${plant.entry.id}`"
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
          <span class="plant-vitality">
            ⚡ <CountUp :value="plant.entry.vitality" />
          </span>
          <span class="plant-updated">
            {{ formatDate(plant.entry.last_interaction_at) }}
          </span>
          <span class="tip" :id="`plant-tip-${plant.entry.id}`">
            <strong>{{ plant.entry.title }}</strong>
            <span>
              ⚡ {{ Math.round(plant.entry.vitality) }} vitality —
              {{ plant.meta.label }}
            </span>
            <span>
              Last interaction:
              {{ formatDate(plant.entry.last_interaction_at) }}
            </span>
            <span>by {{ plant.entry.author.display_name }}</span>
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
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem;
  border-radius: 8px;
  text-decoration: none;
  color: inherit;
  text-align: center;
  /* 450ms (--dur-med) instead of the default 700ms reveal is
   * intentional: the grow-in should feel snappy, not slow-motion.
   * The hover shadow is pre-rendered on ::after (opacity-faded below);
   * box-shadow itself is never transitioned. */
  transition:
    transform var(--dur-med) var(--ease-spring),
    opacity var(--dur-med) var(--ease-spring),
    background-color var(--dur-fast) var(--ease-out);
}

.plant::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 8px;
  box-shadow: 0 10px 24px rgba(35, 80, 50, 0.16);
  opacity: 0;
  transition: opacity var(--dur-fast) var(--ease-out);
  pointer-events: none;
}

.plant:hover::after {
  opacity: 1;
}

/* Grow-in: each plant springs up from the ground (one-shot, staggered).
 * Overrides the global translateY reveal with a bottom-anchored scale. */
.plant.reveal {
  transform: scaleY(0);
  transform-origin: 50% 100%;
}

.plant.reveal.revealed {
  transform: none;
}

.plant.reveal.revealed:hover {
  transform: scale(1.06);
}

.plant:hover {
  background: rgba(47, 143, 78, 0.08);
}

/* Idle sway: living plants move gently, offset per plant via --i so the
 * bed does not swing in lockstep. Withered plants stay perfectly still
 * (dead things don't sway). */
.plant-thriving svg,
.plant-stable svg,
.plant-fading svg {
  transform-box: fill-box;
  transform-origin: 50% 100%;
  animation-delay: calc(var(--i, 0) * -0.7s);
}

.plant-thriving svg {
  animation: sway 4s ease-in-out infinite alternate;
}

.plant-stable svg {
  animation: sway-soft 5s ease-in-out infinite alternate;
}

.plant-fading svg {
  animation: sway-faint 6.5s ease-in-out infinite alternate;
}

@keyframes sway {
  from {
    transform: rotate(-1.5deg);
  }
  to {
    transform: rotate(1.5deg);
  }
}

@keyframes sway-soft {
  from {
    transform: rotate(-0.8deg);
  }
  to {
    transform: rotate(0.8deg);
  }
}

@keyframes sway-faint {
  from {
    transform: rotate(-0.5deg);
  }
  to {
    transform: rotate(0.5deg);
  }
}

/* Withered plants droop and fade. */
.plant-withered svg {
  transform: rotate(10deg);
  opacity: 0.65;
  filter: grayscale(0.6);
}

/* Floating tooltip card (replaces the native title attribute).
 * Width is clamped to 72vw so it never overflows the viewport on narrow
 * screens (a centered tooltip wider than that could stick out on
 * single-column layouts). */
.tip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  width: max-content;
  max-width: min(12rem, 72vw);
  display: grid;
  gap: 2px;
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  background: rgba(28, 30, 33, 0.92);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 400;
  text-align: left;
  white-space: normal;
  opacity: 0;
  transform: translate(-50%, 8px);
  transition:
    opacity var(--dur-fast) var(--ease-out),
    transform var(--dur-fast) var(--ease-spring);
  pointer-events: none;
  z-index: 5;
}

.plant:hover .tip,
.plant:focus-visible .tip {
  opacity: 1;
  transform: translate(-50%, 0);
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
