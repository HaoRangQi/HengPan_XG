<template>
  <div ref="rootRef" class="relative">
    <button type="button" class="icon-btn" :class="open && 'icon-btn-tonal'" aria-label="主题与配色"
      :aria-expanded="open" @click="open = !open">
      <MIcon name="palette" :filled="open" />
    </button>

    <Transition name="pop">
      <div v-if="open" class="dialog absolute right-0 top-12 z-50 w-[340px] origin-top-right p-5" role="dialog"
        aria-label="主题与配色">
        <div class="flex items-center justify-between">
          <h2 class="text-title-m">主题与配色</h2>
          <button type="button" class="icon-btn -mr-2" aria-label="关闭" @click="open = false">
            <MIcon name="close" :size="20" />
          </button>
        </div>
        <p class="mt-1 text-body-s text-md-on-surface-variant">Material You 动态取色：选一个种子色，整套界面随之生成。</p>

        <!-- 种子色：每个圆按该种子色实际生成的配色三分着色，和安卓的壁纸取色一样 -->
        <div class="mt-4 grid grid-cols-4 gap-3">
          <button v-for="preset in swatches" :key="preset.seed" type="button" class="swatch"
            :class="preset.seed.toLowerCase() === theme.seed.toLowerCase() && 'is-selected'"
            :title="preset.name" :aria-label="`种子色：${preset.name}`" @click="setSeed(preset.seed)">
            <span class="swatch-top" :style="{ background: preset.colors.primary }"></span>
            <span class="swatch-left" :style="{ background: preset.colors.secondaryContainer }"></span>
            <span class="swatch-right" :style="{ background: preset.colors.tertiaryContainer }"></span>
            <span class="swatch-check"><MIcon name="check" :size="18" /></span>
          </button>
          <!-- 自定义取色 -->
          <label class="swatch swatch-custom" :class="isCustom && 'is-selected'" title="自定义颜色">
            <input type="color" :value="theme.seed" class="sr-only" @input="onCustom($event.target.value)">
            <span v-if="isCustom" class="absolute inset-0 rounded-full" :style="{ background: theme.seed }"></span>
            <MIcon :name="isCustom ? 'check' : 'colorize'" :size="20" class="relative" />
          </label>
        </div>

        <h3 class="mt-5 text-label-m text-md-on-surface-variant">配色风格</h3>
        <div class="segmented segmented-sm mt-2 w-full">
          <button v-for="variant in SCHEME_VARIANTS" :key="variant.key" type="button" class="flex-1"
            :class="theme.variant === variant.key && 'is-selected'" @click="setVariant(variant.key)">
            {{ variant.label }}
          </button>
        </div>

        <h3 class="mt-5 text-label-m text-md-on-surface-variant">外观</h3>
        <div class="segmented segmented-sm mt-2 w-full">
          <button v-for="mode in THEME_MODES" :key="mode.key" type="button" class="flex-1"
            :class="theme.mode === mode.key && 'is-selected'" @click="setMode(mode.key)">
            <MIcon :name="theme.mode === mode.key ? 'check' : mode.icon" :size="16" />
            {{ mode.label }}
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import MIcon from './MIcon.vue';
import {
  SEED_PRESETS, SCHEME_VARIANTS, THEME_MODES, buildScheme, setMode, setSeed, setVariant, useTheme,
} from './theme.js';

const theme = useTheme();
const open = ref(false);
const rootRef = ref(null);

// 预览色跟着当前的配色风格和明暗一起变
const swatches = computed(() => SEED_PRESETS.map((preset) => ({
  ...preset,
  colors: buildScheme(preset.seed, theme.variant, theme.isDark),
})));
const isCustom = computed(() => !SEED_PRESETS.some((p) => p.seed.toLowerCase() === theme.seed.toLowerCase()));

let customTimer = null;
function onCustom (value) {
  // 拖动取色器时事件很密，稍微节流一下
  clearTimeout(customTimer);
  customTimer = setTimeout(() => setSeed(value), 60);
}

function onDocumentClick (event) {
  if (open.value && rootRef.value && !rootRef.value.contains(event.target)) open.value = false;
}
function onKey (event) {
  if (event.key === 'Escape') open.value = false;
}
onMounted(() => {
  document.addEventListener('pointerdown', onDocumentClick);
  document.addEventListener('keydown', onKey);
});
onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentClick);
  document.removeEventListener('keydown', onKey);
});
</script>

<style scoped>
.swatch {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 9999px;
  overflow: hidden;
  display: grid;
  place-items: center;
  background: var(--md-surface-container-highest);
  outline: 2px solid transparent;
  outline-offset: 3px;
  transition: outline-color var(--md-duration-short) var(--md-ease-standard),
    transform var(--md-duration-medium) var(--md-ease-spring),
    border-radius var(--md-duration-medium) var(--md-ease-emphasized);
  cursor: pointer;
}
.swatch:hover { transform: scale(1.06); }
.swatch.is-selected {
  outline-color: var(--md-primary);
  border-radius: 18px;   /* 选中时从圆变成圆角方形，M3 的形状变化 */
}
.swatch-top, .swatch-left, .swatch-right { position: absolute; }
.swatch-top { inset: 0 0 50% 0; }
.swatch-left { inset: 50% 50% 0 0; }
.swatch-right { inset: 50% 0 0 50%; }
.swatch-check {
  position: relative;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 9999px;
  background: var(--md-primary);
  color: var(--md-on-primary);
  transform: scale(0);
  transition: transform var(--md-duration-medium) var(--md-ease-spring);
}
.swatch.is-selected .swatch-check { transform: scale(1); }
.swatch-custom {
  color: var(--md-on-surface-variant);
  border: 1px dashed var(--md-outline);
}
.swatch-custom.is-selected { color: #fff; border-style: solid; }
</style>
