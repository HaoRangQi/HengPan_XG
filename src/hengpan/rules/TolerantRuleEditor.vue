<template>
  <RuleEditorTable :rules="rules" :fields="fields" :max-rules="maxRules"
    @add="emit('add')" @remove="emit('remove', $event)" />
</template>

<script setup>
import RuleEditorTable from './RuleEditorTable.vue';
import { fieldEntriesForMode } from '../ruleModes.js';

defineProps({ rules: { type: Array, required: true }, maxRules: { type: Number, required: true } });
const emit = defineEmits(['add', 'remove']);
const fields = fieldEntriesForMode('tolerant').map(([key, field]) => ({ key, ...field }));
</script>
