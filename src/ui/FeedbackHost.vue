<template>
  <!-- 确认对话框 -->
  <Transition name="fade">
    <div v-if="state.dialog" class="dialog-scrim flex items-center justify-center p-6" @click.self="settle(false)">
      <Transition name="pop" appear>
        <div class="dialog w-full max-w-[400px] p-6" role="alertdialog" :aria-label="state.dialog.title">
          <div v-if="state.dialog.icon" class="mb-4 flex justify-center">
            <MIcon :name="state.dialog.icon" :size="28" :class="state.dialog.danger ? 'text-md-error' : 'text-md-secondary'" />
          </div>
          <h2 class="text-headline-s" :class="state.dialog.icon && 'text-center'">{{ state.dialog.title }}</h2>
          <p v-if="state.dialog.message" class="mt-4 whitespace-pre-line text-body-m text-md-on-surface-variant">
            {{ state.dialog.message }}
          </p>
          <div class="mt-6 flex justify-end gap-2">
            <button type="button" class="btn btn-text" @click="settle(false)">{{ state.dialog.cancelText }}</button>
            <button ref="confirmRef" type="button" class="btn" :class="state.dialog.danger ? 'btn-danger' : 'btn-filled'"
              @click="settle(true)">
              {{ state.dialog.confirmText }}
            </button>
          </div>
        </div>
      </Transition>
    </div>
  </Transition>

  <!-- Snackbar -->
  <div class="pointer-events-none fixed inset-x-0 bottom-24 z-[70] flex justify-center px-4 lg:bottom-6">
    <Transition name="snack">
      <div v-if="state.snackbar" :key="state.snackbar.id"
        class="snackbar pointer-events-auto" :class="`is-${state.snackbar.tone}`" role="status">
        <MIcon :name="toneIcon" :size="20" class="shrink-0" />
        <span class="min-w-0 flex-1">{{ state.snackbar.message }}</span>
        <button v-if="state.snackbar.action" type="button" class="snack-action"
          @click="state.snackbar.action.handler(); dismiss()">{{ state.snackbar.action.label }}</button>
        <button type="button" class="snack-close" aria-label="关闭" @click="dismiss">
          <MIcon name="close" :size="18" />
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import MIcon from './MIcon.vue';
import { feedbackState as state, useFeedback } from './feedback.js';

const { settle, dismiss } = useFeedback();
const confirmRef = ref(null);

const toneIcon = computed(() => ({
  success: 'check_circle', error: 'error', warn: 'warning',
})[state.snackbar?.tone] || 'info');

// 对话框打开后把焦点放到确认按钮上，回车即可确认
watch(() => state.dialog, (dialog) => { if (dialog) nextTick(() => confirmRef.value?.focus()); });

function onKey (event) {
  if (event.key === 'Escape' && state.dialog) settle(false);
}
onMounted(() => document.addEventListener('keydown', onKey));
onUnmounted(() => document.removeEventListener('keydown', onKey));
</script>

<style scoped>
.snackbar {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  max-width: 560px;
  padding: 6px 8px 6px 16px;
  border-radius: var(--md-shape-sm);
  background: var(--md-inverse-surface);
  color: var(--md-inverse-on-surface);
  box-shadow: var(--md-elevation-3);
  font-size: 14px;
  line-height: 20px;
}
.snackbar.is-success :first-child { color: var(--md-inverse-primary); }
.snackbar.is-error :first-child { color: #ffb4ab; }
.snack-action {
  padding: 8px 12px;
  border-radius: 9999px;
  color: var(--md-inverse-primary);
  font-weight: 500;
}
.snack-close {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 9999px;
  opacity: 0.8;
}
.snack-close:hover, .snack-action:hover { background: color-mix(in srgb, currentColor 10%, transparent); }
.snack-enter-active { transition: opacity 200ms var(--md-ease-emphasized-decelerate), transform 400ms var(--md-ease-spring); }
.snack-leave-active { transition: opacity 150ms var(--md-ease-emphasized-accelerate), transform 150ms var(--md-ease-emphasized-accelerate); }
.snack-enter-from { opacity: 0; transform: translateY(24px) scale(0.96); }
.snack-leave-to { opacity: 0; transform: translateY(8px); }
</style>
