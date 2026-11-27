<script setup lang="ts">
import type { Field, Row } from '../mock/catalog'
import EmptyState from './EmptyState.vue'
import StatusTag from './StatusTag.vue'
defineProps<{ fields: Field[]; rows: Row[]; editable?: boolean; loading?: boolean }>()
defineEmits<{ detail: [Row]; edit: [Row]; remove: [Row] }>()
</script>
<template>
  <div class="table-scroll" :aria-busy="loading">
    <div v-if="loading" class="empty" role="status">数据加载中…</div>
    <EmptyState v-else-if="!rows.length" />
    <table v-else>
      <thead>
        <tr>
          <th v-for="f in fields" :key="f.key">{{ f.label }}</th>
          <th v-if="$slots.actions || editable || $attrs.onDetail">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id">
          <td v-for="f in fields" :key="f.key">
            <StatusTag
              v-if="f.key === 'status' || f.key === 'severity'"
              :value="row[f.key] || '—'"
            /><template v-else>{{ row[f.key] || '—' }}</template>
          </td>
          <td v-if="$slots.actions || editable || $attrs.onDetail">
            <slot name="actions" :row="row"
              ><button class="link" @click="$emit('detail', row)">详情</button
              ><button v-if="editable" class="link" @click="$emit('edit', row)">编辑</button
              ><button v-if="editable" class="link danger" @click="$emit('remove', row)">
                删除
              </button></slot
            >
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
