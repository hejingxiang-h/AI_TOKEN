<script setup lang="ts">
defineProps<{ tone: 'good' | 'bad' | 'neutral'; label: string }>()
</script>

<template>
  <span class="status-pill" :class="'status-pill--' + tone">
    <span aria-hidden="true"></span>
    {{ label }}
  </span>
</template>
