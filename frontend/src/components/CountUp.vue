<script setup lang="ts">
import { toRef } from 'vue'

import { useCountUp } from '../composables/useCountUp'

// Inline animated number (vitality counts in the garden / document views).
const props = defineProps<{ value: number; duration?: number }>()
const display = useCountUp(toRef(props, 'value'), props.duration ?? 900)
</script>

<template>{{ display }}</template>
