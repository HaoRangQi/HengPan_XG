<template>
  <a :href="historyLink(kind)" class="btn btn-text btn-sm h-8 shrink-0 px-2 text-xs" title="统一查看、备注和清理扫描历史">
    <MIcon name="history" :size="17" />历史管理
  </a>
</template>

<script setup>
import MIcon from '../ui/MIcon.vue';
import { historyLink } from '../views/historyPresentation.js';
defineProps({ kind: { type: String, required: true } });
</script>
