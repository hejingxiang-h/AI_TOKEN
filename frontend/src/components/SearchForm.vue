<script setup lang="ts">
const query = defineModel<string>('query', { required: true })
const status = defineModel<string>('status', { required: true })
defineProps<{ options: string[] }>()
defineEmits<{ search: []; reset: [] }>()
</script>
<template>
  <form class="search" @submit.prevent="$emit('search')">
    <label>关键词<input v-model="query" placeholder="搜索名称或其他字段" /></label
    ><label v-if="options.length"
      >状态<select v-model="status">
        <option value="">全部状态</option>
        <option v-for="o in options" :key="o">{{ o }}</option>
      </select></label
    ><button class="primary" type="submit">搜索</button
    ><button type="button" @click="$emit('reset')">重置</button>
  </form>
</template>
