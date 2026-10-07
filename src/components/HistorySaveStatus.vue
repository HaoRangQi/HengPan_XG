<template>
  <div v-if="state.status === 'pending' || state.status === 'failed'" class="m-5 rounded-lg border border-border bg-muted p-3 text-sm" role="status" aria-live="polite">
    <p>{{ state.status === 'failed' ? '历史保存失败' : '历史保存尚未确认' }}。当前扫描结果仍可查看。</p>
    <p v-if="state.error" class="mt-1 break-words text-xs text-destructive">{{ state.error }}</p>
    <p v-else class="mt-1 text-xs text-muted-foreground">扫描已结束，后台可能仍在保存；稍后可重试确认。</p>
    <button type="button" class="btn-quiet mt-2 h-8 px-3 text-xs" :disabled="state.busy" @click="$emit('retry')">{{ state.busy ? '正在确认保存…' : '重试保存历史' }}</button>
  </div>
</template>
<script setup>
defineProps({ state: { type: Object, required: true } });
defineEmits(['retry']);
</script>
