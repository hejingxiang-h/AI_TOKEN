<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ value: string }>()
const tone = computed(() =>
  ['启用', '成功', '已结案', '低'].includes(props.value)
    ? 'good'
    : ['失败', '高', '停用'].includes(props.value)
      ? 'bad'
      : 'wait',
)
</script>
<template>
  <span class="tag" :class="'tag-' + tone"><i></i>{{ value }}</span>
</template>
