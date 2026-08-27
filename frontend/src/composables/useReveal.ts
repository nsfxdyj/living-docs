import { onBeforeUnmount, onMounted, type Ref } from 'vue'

/**
 * Reveal-on-scroll: adds `.revealed` to every `.reveal` element inside
 * `root` the first time it enters the viewport (one-shot).
 *
 * Optional per-element `data-stagger="<n>"` adds an `n * staggerStep`
 * transition delay; the delay is cleared once the transition ends so
 * later interactions (e.g. hover) on the same element are not delayed.
 *
 * Content rendered after async fetches is picked up via MutationObserver,
 * so views only need `ref="root"` plus `class="reveal"` in the template.
 * Under prefers-reduced-motion elements are revealed immediately.
 */
export function useReveal(
  root: Ref<HTMLElement | null>,
  staggerStep = 80,
): void {
  let observer: IntersectionObserver | null = null
  let mutations: MutationObserver | null = null
  const registered = new WeakSet<Element>()
  const revealed = new WeakSet<Element>()
  const timers = new Set<number>()
  const reduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  function reveal(el: Element): void {
    observer?.unobserve(el)
    el.classList.add('revealed')
    revealed.add(el)
    const delay = Number((el as HTMLElement).dataset.stagger ?? 0) * staggerStep
    if (delay > 0) {
      const target = el as HTMLElement
      let timer = 0
      const clearDelay = (): void => {
        target.style.transitionDelay = ''
        target.removeEventListener('transitionend', onEnd)
        window.clearTimeout(timer)
        timers.delete(timer)
      }
      const onEnd = (event: Event): void => {
        // transitionend bubbles; only the reveal transition on the
        // element itself should clear its stagger delay.
        if (event.target === target) clearDelay()
      }
      target.addEventListener('transitionend', onEnd)
      // Fallback in case transitionend never fires (e.g. the element is
      // removed or the transition is interrupted).
      timer = window.setTimeout(clearDelay, delay + 1200)
      timers.add(timer)
    }
  }

  function register(el: Element): void {
    if (registered.has(el)) return
    registered.add(el)
    const index = Number((el as HTMLElement).dataset.stagger ?? 0)
    if (!reduced && index > 0) {
      ;(el as HTMLElement).style.transitionDelay = `${index * staggerStep}ms`
    }
    if (reduced) {
      el.classList.add('revealed')
      revealed.add(el)
      return
    }
    observer?.observe(el)
  }

  function scan(): void {
    const el = root.value
    if (el === null) return
    if (el.classList.contains('reveal')) register(el)
    el.querySelectorAll('.reveal').forEach(register)
  }

  function onMutations(records: MutationRecord[]): void {
    let rescan = false
    for (const record of records) {
      // Vue's declarative class binding rewrites `class` on re-render
      // (e.g. the workspace list after a search), which would silently
      // drop our `.revealed`; put it back on elements already revealed.
      if (record.type === 'attributes') {
        const el = record.target
        if (revealed.has(el) && !el.classList.contains('revealed')) {
          el.classList.add('revealed')
        }
      } else {
        rescan = true
      }
    }
    if (rescan) scan()
  }

  onMounted(() => {
    if (reduced) {
      scan()
      return
    }
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) reveal(entry.target)
        }
      },
      // threshold 0: any visible pixel counts, so elements taller than
      // the viewport (e.g. a long document body) still reveal.
      { threshold: 0, rootMargin: '0px 0px -8% 0px' },
    )
    // Views render their content after async fetches, so keep watching
    // for late-added `.reveal` nodes.
    mutations = new MutationObserver(onMutations)
    scan()
    if (root.value !== null) {
      mutations.observe(root.value, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class'],
      })
    }
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    mutations?.disconnect()
    for (const timer of timers) window.clearTimeout(timer)
    timers.clear()
  })
}
