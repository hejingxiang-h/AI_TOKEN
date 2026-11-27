<script setup lang="ts">
defineProps<{ label: string; value: string; note: string; icon: string }>()
</script>
<template>
  <article class="card metric">
    <div>
      <span>{{ label }}</span><b>{{ value }}</b
      ><small>{{ note }}</small>
    </div>
    <i aria-hidden="true">{{ icon }}</i>
  </article>
</template>
