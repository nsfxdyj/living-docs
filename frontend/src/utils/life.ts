// Shared life-system presentation logic (M4).
// One source of truth for status colors used by the garden, the document
// list and the document page badges.

export type LifeStatus = 'thriving' | 'stable' | 'fading' | 'withered'

export const LIFE_STATUSES: LifeStatus[] = [
  'thriving',
  'stable',
  'fading',
  'withered',
]

export interface StatusMeta {
  label: string
  /** Foreground (text) color. */
  color: string
  /** Badge background color. */
  background: string
  /** Plant leaf color in the garden. */
  leaf: string
  /** Plant stem color in the garden. */
  stem: string
}

export const STATUS_META: Record<LifeStatus, StatusMeta> = {
  thriving: {
    label: 'Thriving',
    color: '#1d6b3c',
    background: '#d9f2e3',
    leaf: '#2f8f4e',
    stem: '#256b3a',
  },
  stable: {
    label: 'Stable',
    color: '#2c5aa0',
    background: '#e3ecfb',
    leaf: '#5b8dd9',
    stem: '#3d6ab0',
  },
  fading: {
    label: 'Fading',
    color: '#8a6d1d',
    background: '#fbf0d4',
    leaf: '#d4a017',
    stem: '#a07c14',
  },
  withered: {
    label: 'Withered',
    color: '#666666',
    background: '#e4e4e4',
    leaf: '#9a9a9a',
    stem: '#7d7d7d',
  },
}

export function lifeStatus(status: string): LifeStatus {
  return (LIFE_STATUSES as string[]).includes(status)
    ? (status as LifeStatus)
    : 'withered'
}

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[lifeStatus(status)]
}

/** Inline style for the status badge, shared by list and document views. */
export function badgeStyle(status: string): Record<string, string> {
  const meta = statusMeta(status)
  return { color: meta.color, background: meta.background }
}

/**
 * Plant size (SVG pixel width) for the garden: scales with vitality,
 * capped so a single hot document does not dominate the whole garden.
 */
export function plantSize(vitality: number): number {
  const capped = Math.min(Math.max(vitality, 0), 120)
  return Math.round(56 + (capped / 120) * 72) // 56px .. 128px
}
