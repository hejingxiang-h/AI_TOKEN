<script setup lang="ts">
import { ElDialog } from 'element-plus'
const open = defineModel<boolean>({ required: true })
defineProps<{ title: string; description: string }>()
defineEmits<{ confirm: [] }>()
</script>
<template>
  <ElDialog v-model="open" :title="title" width="min(420px, 94vw)"
    ><p>{{ description }}</p>
    <div class="modal-actions">
      <button @click="open = false">取消</button
      ><button class="primary delete" @click="$emit('confirm')">确认</button>
    </div></ElDialog
  >
</template>
