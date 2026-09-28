<template>
  <div class="mt-4 overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="text-left text-xs text-muted-foreground">
          <th class="w-10 pb-2 font-normal">组</th>
          <th v-for="field in fields" :key="field.key" class="pb-2 pr-4 font-normal">
            {{ field.label }}<span class="ml-1">（{{ field.unit }}）</span>
          </th>
          <th class="w-10 pb-2"><span class="sr-only">删除</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(rule, index) in rules" :key="index" class="border-t border-border">
          <td class="py-2 text-xs text-muted-foreground tabular-nums">{{ index + 1 }}</td>
          <td v-for="field in fields" :key="field.key" class="py-2 pr-4">
            <input v-model.number="rule[field.key]" class="input h-9 w-full min-w-[7rem]" type="number"
              :step="field.step" :min="field.min" :max="field.max" :placeholder="field.placeholder || ''"
              :aria-label="`第 ${index + 1} 组 ${field.label}`">
          </td>
          <td class="py-2">
            <button v-if="rules.length > 1" type="button" class="help-btn"
              :aria-label="`删除第 ${index + 1} 组规则`" title="删除这一组" @click="emit('remove', index)">
              <MIcon name="close" :size="20" />
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <button v-if="rules.length < maxRules" type="button" class="btn-quiet mt-3 h-8 px-3" @click="emit('add')">
    <MIcon name="add" :size="18" />添加一组
  </button>
</template>

<script setup>
defineProps({
  rules: { type: Array, required: true },
  fields: { type: Array, required: true },
  maxRules: { type: Number, required: true },
});
const emit = defineEmits(['add', 'remove']);
</script>
