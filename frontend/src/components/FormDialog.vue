<script setup lang="ts">
import { ElDialog } from 'element-plus'
const open = defineModel<boolean>({ required: true })
defineProps<{ title: string; readonly?: boolean }>()
defineEmits<{ submit: [] }>()
</script>
<template>
  <ElDialog v-model="open" :title="title" width="min(530px, 94vw)" destroy-on-close
    ><form @submit.prevent="$emit('submit')">
      <slot />
      <div class="modal-actions">
        <button type="button" @click="open = false">{{ readonly ? '关闭' : '取消' }}</button><button
          v-if="!readonly"
          type="submit"
          class="primary"
        >
          保存
        </button>
      </div>
    </form></ElDialog
  >
</template>
