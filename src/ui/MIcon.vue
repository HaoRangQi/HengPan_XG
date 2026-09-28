<template>
  <span :class="['m-icon', filled && 'is-filled']" :style="style" aria-hidden="true">{{ name }}</span>
</template>

<script setup>
/**
 * Material Symbols 图标（Rounded，本地打包，不走 Google CDN）。
 *   <MIcon name="search" />  <MIcon name="star" filled :size="20" />
 * 图标名见 https://fonts.google.com/icons
 */
import { computed } from 'vue';

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: null },
  filled: { type: Boolean, default: false },
  weight: { type: Number, default: null },
});

const style = computed(() => {
  const result = {};
  if (props.size) result.fontSize = typeof props.size === 'number' ? `${props.size}px` : props.size;
  if (props.weight) {
    result.fontVariationSettings = `"FILL" ${props.filled ? 1 : 0}, "wght" ${props.weight}, "GRAD" 0, "opsz" 24`;
  }
  return result;
});
</script>
