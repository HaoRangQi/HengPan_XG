<template>
  <div class="parameter-tooltip-container">
    <div ref="trigger" @mouseenter="showTooltip = true" @mouseleave="handleMouseLeave" class="tooltip-trigger">
      <slot>
        <!-- 默认内容，如果没有传递内容则显示 -->
      </slot>
      <span class="info-icon">
        <i class="fas fa-circle-info"></i>
      </span>
    </div>

    <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100" leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 scale-100" leave-to-class="opacity-0 scale-95">
      <div v-if="showTooltip" ref="tooltip" @mouseenter="isHoveringTooltip = true"
        @mouseleave="isHoveringTooltip = false" class="tooltip-content" :class="[position]">
        <div class="tooltip-inner">
          <div class="tooltip-title">{{ title }}</div>
          <div class="tooltip-description">{{ description }}</div>
          <button @click="$emit('show-tutorial', id)" class="tooltip-button">
            查看详情
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue';

const props = defineProps({
  id: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    required: true
  },
  position: {
    type: String,
    default: 'top',
    validator: (value) => ['top', 'bottom', 'left', 'right'].includes(value)
  }
});

defineEmits(['show-tutorial']);

const showTooltip = ref(false);
const isHoveringTooltip = ref(false);
const trigger = ref(null);
const tooltip = ref(null);

const handleMouseLeave = () => {
  setTimeout(() => {
    if (!isHoveringTooltip.value) {
      showTooltip.value = false;
    }
  }, 100);
};

watch(isHoveringTooltip, (newValue) => {
  if (!newValue) {
    setTimeout(() => {
      if (!isHoveringTooltip.value) {
        showTooltip.value = false;
      }
    }, 100);
  }
});

// 处理点击外部关闭
const handleClickOutside = (event) => {
  if (
    showTooltip.value &&
    tooltip.value &&
    !tooltip.value.contains(event.target) &&
    trigger.value &&
    !trigger.value.contains(event.target)
  ) {
    showTooltip.value = false;
  }
};

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>

<style scoped>
.parameter-tooltip-container {
  position: relative;
  display: inline-block;
}

.tooltip-trigger {
  display: inline-flex;
  align-items: center;
  cursor: help;
}

.info-icon {
  margin-left: 0.375rem;
  font-size: 1rem;
  color: var(--md-primary);
  opacity: 0.75;
  transition: all 0.2s;
  cursor: help;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--md-primary) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--md-primary) 24%, transparent);
}

.info-icon:hover {
  opacity: 1;
  transform: scale(1.1);
  background: color-mix(in srgb, var(--md-primary) 16%, transparent);
  border-color: color-mix(in srgb, var(--md-primary) 36%, transparent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--md-primary) 12%, transparent);
}

.tooltip-content {
  position: absolute;
  z-index: 70;
  width: min(280px, calc(100vw - 32px));
}

.tooltip-content.top {
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(-8px);
}

.tooltip-content.bottom {
  top: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(8px);
}

.tooltip-content.left {
  right: 100%;
  top: 50%;
  transform: translateY(-50%) translateX(-8px);
}

.tooltip-content.right {
  left: 100%;
  top: 50%;
  transform: translateY(-50%) translateX(8px);
}

.tooltip-inner {
  padding: 14px;
  border-radius: var(--md-shape-sm);
  background: var(--md-inverse-surface);
  color: var(--md-inverse-on-surface);
  box-shadow: var(--md-elevation-3);
}

.tooltip-title {
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: var(--md-inverse-on-surface);
}

.tooltip-description {
  margin-bottom: 0.75rem;
  line-height: 1.4;
  color: var(--md-inverse-on-surface);
}

.tooltip-button {
  background: var(--md-primary);
  color: var(--md-on-primary);
  font-size: 0.75rem;
  padding: 0.25rem 0.75rem;
  border-radius: 0.25rem;
  border: none;
  cursor: pointer;
  transition: background-color var(--md-duration-short) var(--md-ease-standard),
    transform var(--md-duration-short) var(--md-ease-standard);
}

.tooltip-button:hover {
  background: color-mix(in srgb, var(--md-primary) 88%, var(--md-on-primary));
  transform: translateY(-1px);
}
</style>
