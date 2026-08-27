import { onScopeDispose, ref, watch, type Ref } from 'vue'

/**
 * Animated number: eases (easeOutCubic, requestAnimationFrame) from the
 * previous value to `target` whenever it changes. Returns the rounded
 * display value. Under prefers-reduced-motion the value snaps instantly.
 */
export function useCountUp(target: Ref<number>, duration = 900): Ref<number> {
  const display = ref(0)
  let frame = 0
  const reduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  function animateTo(from: number, to: number): void {
    cancelAnimationFrame(frame)
    if (reduced || duration <= 0 || from === to) {
      display.value = Math.round(to)
      return
    }
    const start = performance.now()
    const tick = (now: number): void => {
      const t = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - t, 3) // easeOutCubic
      display.value = Math.round(from + (to - from) * eased)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
  }

  // Animate from the *currently displayed* value, so retargeting
  // mid-animation does not jump back to the previous target.
  watch(target, (to) => animateTo(display.value, to), { immediate: true })
  onScopeDispose(() => cancelAnimationFrame(frame))
  return display
}
