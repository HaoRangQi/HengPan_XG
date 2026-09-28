/**
 * Material You 动态取色。
 *
 * 用 Google 官方的 material-color-utilities 从一个种子色算出整套 M3 色彩角色，
 * 写到 <html> 的 CSS 变量上（--md-primary、--md-surface-container-low …）。
 * 所有页面和图表都从这些变量取色，换种子色 = 整站换肤。
 */
import { reactive, readonly, onMounted, onUnmounted, ref } from 'vue';
import {
  Hct, argbFromHex, hexFromArgb, MaterialDynamicColors,
  SchemeTonalSpot, SchemeVibrant, SchemeExpressive, SchemeContent,
} from '@material/material-color-utilities';

const STORAGE_KEY = 'm3-theme';

// 预设种子色：挑了几组在亮暗两种模式下都耐看的颜色
export const SEED_PRESETS = [
  { name: '薰衣草', seed: '#6750A4' },
  { name: '谷歌蓝', seed: '#0B57D0' },
  { name: '青瓷', seed: '#006A6A' },
  { name: '竹青', seed: '#3B6939' },
  { name: '琥珀', seed: '#8C5000' },
  { name: '胭脂', seed: '#9C4146' },
  { name: '墨灰', seed: '#5C5F66' },
];

// 配色风格：同一个种子色，饱和度与色相分布不同
export const SCHEME_VARIANTS = [
  { key: 'tonal', label: '柔和', Scheme: SchemeTonalSpot },
  { key: 'vibrant', label: '鲜艳', Scheme: SchemeVibrant },
  { key: 'expressive', label: '表现力', Scheme: SchemeExpressive },
  { key: 'content', label: '忠于原色', Scheme: SchemeContent },
];

export const THEME_MODES = [
  { key: 'light', label: '浅色', icon: 'light_mode' },
  { key: 'dark', label: '深色', icon: 'dark_mode' },
  { key: 'system', label: '自动', icon: 'brightness_auto' },
];

const ROLES = [
  'primary', 'onPrimary', 'primaryContainer', 'onPrimaryContainer',
  'secondary', 'onSecondary', 'secondaryContainer', 'onSecondaryContainer',
  'tertiary', 'onTertiary', 'tertiaryContainer', 'onTertiaryContainer',
  'error', 'onError', 'errorContainer', 'onErrorContainer',
  'surface', 'onSurface', 'surfaceVariant', 'onSurfaceVariant', 'surfaceDim', 'surfaceBright',
  'surfaceContainerLowest', 'surfaceContainerLow', 'surfaceContainer',
  'surfaceContainerHigh', 'surfaceContainerHighest',
  'outline', 'outlineVariant', 'inverseSurface', 'inverseOnSurface', 'inversePrimary',
  'scrim', 'shadow', 'surfaceTint',
];
const kebab = (name) => name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
const dynamicColors = new MaterialDynamicColors();

/** 由种子色生成一套色彩角色：{ primary: '#xxxxxx', onPrimary: … } */
export function buildScheme (seed, variantKey = 'tonal', dark = false) {
  const variant = SCHEME_VARIANTS.find((v) => v.key === variantKey) || SCHEME_VARIANTS[0];
  const scheme = new variant.Scheme(Hct.fromInt(argbFromHex(seed)), dark, 0);
  return Object.fromEntries(ROLES.map((role) => [role, hexFromArgb(dynamicColors[role]().getArgb(scheme))]));
}

function loadSaved () {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    // 兼容旧的明暗开关（localStorage.theme = 'dark' / 'light'）
    const legacyMode = localStorage.getItem('theme');
    return {
      seed: /^#[0-9a-f]{6}$/i.test(saved.seed || '') ? saved.seed : SEED_PRESETS[0].seed,
      variant: SCHEME_VARIANTS.some((v) => v.key === saved.variant) ? saved.variant : 'tonal',
      mode: THEME_MODES.some((m) => m.key === saved.mode) ? saved.mode
        : (legacyMode === 'dark' || legacyMode === 'light' ? legacyMode : 'system'),
    };
  } catch {
    return { seed: SEED_PRESETS[0].seed, variant: 'tonal', mode: 'system' };
  }
}

const systemDark = typeof window !== 'undefined' && window.matchMedia
  ? window.matchMedia('(prefers-color-scheme: dark)') : null;

const state = reactive({ ...loadSaved(), isDark: false, colors: {} });
let transitionTimer = null;

function resolveDark () {
  return state.mode === 'dark' || (state.mode === 'system' && !!systemDark?.matches);
}

/** 计算并写入 CSS 变量；animate 为 true 时整站颜色平滑过渡 */
function apply (animate = false) {
  const root = document.documentElement;
  if (animate) {
    root.classList.add('theme-transition');
    clearTimeout(transitionTimer);
    transitionTimer = setTimeout(() => root.classList.remove('theme-transition'), 500);
  }
  state.isDark = resolveDark();
  const colors = buildScheme(state.seed, state.variant, state.isDark);
  for (const [role, hex] of Object.entries(colors)) root.style.setProperty(`--md-${kebab(role)}`, hex);
  root.classList.toggle('dark', state.isDark);
  root.style.colorScheme = state.isDark ? 'dark' : 'light';
  state.colors = colors;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', colors.surface);
  // 旧代码读 localStorage.theme 判断明暗，保持同步
  localStorage.setItem('theme', state.isDark ? 'dark' : 'light');
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ seed: state.seed, variant: state.variant, mode: state.mode }));
  window.dispatchEvent(new CustomEvent('m3-theme-change', { detail: { isDark: state.isDark, colors } }));
}

/** 应用启动时调用一次（在挂载前），避免首屏闪烁 */
export function initTheme () {
  apply(false);
  systemDark?.addEventListener('change', () => { if (state.mode === 'system') apply(true); });
}

export function setSeed (seed) { state.seed = seed; apply(true); }
export function setVariant (variant) { state.variant = variant; apply(true); }
export function setMode (mode) { state.mode = mode; apply(true); }
export function toggleDark () { setMode(state.isDark ? 'light' : 'dark'); }

/** 组件里读主题状态：const theme = useTheme(); theme.isDark / theme.colors.primary */
export function useTheme () {
  return readonly(state);
}

/**
 * 给图表用：返回当前主题色（响应式），并在主题变化时回调。
 *   const { colors } = useM3Colors(() => chart.setOption(buildOption()));
 * colors.value.primary / onSurfaceVariant / outlineVariant / rise / fall …
 */
export function useM3Colors (onChange) {
  const colors = ref(currentColors());
  const handler = () => {
    colors.value = currentColors();
    if (onChange) onChange(colors.value);
  };
  onMounted(() => window.addEventListener('m3-theme-change', handler));
  onUnmounted(() => window.removeEventListener('m3-theme-change', handler));
  return { colors };
}

/** 从 CSS 变量读一份当前配色（含涨跌色），非组件环境也能用 */
export function currentColors () {
  const style = getComputedStyle(document.documentElement);
  const read = (name) => style.getPropertyValue(`--md-${name}`).trim();
  return {
    ...state.colors,
    rise: read('rise') || '#d93a3a',
    fall: read('fall') || '#1b9e5a',
    isDark: state.isDark,
  };
}
