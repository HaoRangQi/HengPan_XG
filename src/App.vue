<template>
  <div class="min-h-screen bg-md-surface text-md-on-surface">
    <!-- 参数帮助管理器：各页面的参数说明弹窗共用这一个实例 -->
    <ParameterHelpManager />
    <!-- 全局提示条和确认对话框 -->
    <FeedbackHost />

    <!-- 桌面端：Navigation Rail -->
    <nav class="rail" aria-label="主导航">
      <a href="#/" class="rail-brand" aria-label="回到首页">
        <span class="brand-mark"><MIcon name="stacked_line_chart" filled :size="26" /></span>
      </a>
      <button type="button" class="fab rail-fab" title="案例管理" aria-label="案例管理" @click="showCaseManager = true">
        <MIcon name="bookmarks" />
      </button>
      <div class="flex flex-col gap-1">
        <a v-for="item in navItems" :key="item.path" :href="`#${item.path}`" class="nav-item"
          :class="item.path === currentPath && 'is-active'"
          :aria-current="item.path === currentPath ? 'page' : undefined">
          <span class="nav-pill"><MIcon :name="item.icon" :filled="item.path === currentPath" /></span>
          <span class="nav-label">{{ item.short }}</span>
        </a>
      </div>
    </nav>

    <div class="lg:pl-[88px]">
      <!-- Top App Bar：滚动后底色加深 -->
      <header class="top-bar" :class="scrolled && 'is-scrolled'">
        <div class="flex min-w-0 items-center gap-3">
          <span class="brand-mark brand-mark-sm mobile-only"><MIcon name="stacked_line_chart" filled :size="20" /></span>
          <div class="min-w-0">
            <Transition name="title-swap" mode="out-in">
              <div :key="currentPath">
                <h1 class="truncate text-title-l">{{ currentRoute.label }}</h1>
                <p class="hidden truncate text-body-s text-md-on-surface-variant sm:block">{{ currentRoute.desc }}</p>
              </div>
            </Transition>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <button type="button" class="icon-btn lg:hidden" aria-label="案例管理" @click="showCaseManager = true">
            <MIcon name="bookmarks" />
          </button>
          <button type="button" class="icon-btn" :aria-label="theme.isDark ? '切换到浅色' : '切换到深色'"
            :title="theme.isDark ? '切换到浅色' : '切换到深色'" @click="toggleDark">
            <Transition name="icon-spin" mode="out-in">
              <MIcon :key="theme.isDark" :name="theme.isDark ? 'light_mode' : 'dark_mode'" />
            </Transition>
          </button>
          <ThemePicker />
        </div>
      </header>

      <!-- KeepAlive：切换页面时保留扫描进度和结果 -->
      <div class="pb-24 lg:pb-8">
        <Transition name="fade-through" mode="out-in">
          <KeepAlive>
            <component :is="currentRoute.component" :key="currentPath" />
          </KeepAlive>
        </Transition>
      </div>
    </div>

    <!-- 移动端：Navigation Bar -->
    <nav class="bottom-bar" aria-label="主导航">
      <a v-for="item in navItems" :key="item.path" :href="`#${item.path}`" class="nav-item"
        :class="item.path === currentPath && 'is-active'"
        :aria-current="item.path === currentPath ? 'page' : undefined">
        <span class="nav-pill"><MIcon :name="item.icon" :filled="item.path === currentPath" /></span>
        <span class="nav-label">{{ item.short }}</span>
      </a>
    </nav>

    <!-- 案例管理对话框 -->
    <Transition name="fade">
      <div v-if="showCaseManager" class="dialog-scrim flex items-center justify-center p-3 sm:p-6"
        @click.self="showCaseManager = false">
        <Transition name="pop" appear>
          <div class="dialog flex h-[90vh] w-full max-w-6xl flex-col overflow-hidden">
            <div class="flex-1 overflow-auto">
              <CaseManager @close="showCaseManager = false" />
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue';
import { ParameterHelpManager } from './components/parameter-help';
import CaseManager from './components/case-management/CaseManager.vue';
import MIcon from './ui/MIcon.vue';
import ThemePicker from './ui/ThemePicker.vue';
import FeedbackHost from './ui/FeedbackHost.vue';
import { toggleDark, useTheme } from './ui/theme.js';
import ScanView from './views/ScanView.vue';
import LegacyScanView from './views/LegacyScanView.vue';
import DataView from './views/DataView.vue';
import ApiDocsView from './views/ApiDocsView.vue';
import HengpanScanView from './hengpan/HengpanScanView.vue';

// 用 hash 做页面切换，不需要服务端配合，也不必引入 vue-router
const routes = {
  '/': { label: '横盘选股', short: '横盘', icon: 'candlestick_chart', desc: '末端锚定箱体 · 60 分钟与日线扫描', component: HengpanScanView },
  '/platform': { label: '平台扫描', short: '平台', icon: 'radar', desc: '多窗口平台期识别', component: ScanView },
  '/legacy': { label: '旧版扫描', short: '旧版', icon: 'history', desc: '早期版本，保留备查', component: LegacyScanView },
  '/data': { label: '数据管理', short: '数据', icon: 'database', desc: '本地行情库 · A 股与加密货币', component: DataView },
  '/api-docs': { label: '接口文档', short: '接口', icon: 'api', desc: '后端 API 一览', component: ApiDocsView },
};
const navItems = Object.entries(routes).map(([path, route]) => ({ path, ...route }));

const parsePath = () => {
  const path = window.location.hash.replace(/^#/, '') || '/';
  // `/hengpan` 是最早的深链接，旧书签仍然跳到首页
  if (path === '/hengpan') return '/';
  return routes[path] ? path : '/';
};
const currentPath = ref(parsePath());
const currentRoute = computed(() => routes[currentPath.value]);
const onHashChange = () => {
  currentPath.value = parsePath();
  window.scrollTo(0, 0);
};

watch(currentPath, (path) => {
  document.title = `${routes[path].label} · 平台期扫描工具`;
  // KeepAlive 页面重新挂回文档后，让其中的图表按当前尺寸重绘；等页面过渡动画结束再发
  nextTick(() => {
    window.dispatchEvent(new Event('resize'));
    setTimeout(() => window.dispatchEvent(new Event('resize')), 420);
  });
}, { immediate: true });

const showCaseManager = ref(false);

// 主题：旧页面通过 inject('isDarkMode') 给图表判断明暗
const theme = useTheme();
provide('isDarkMode', computed(() => theme.isDark));
provide('toggleDarkMode', toggleDark);

// Top App Bar 滚动后加深底色（M3 scrolled state）
const scrolled = ref(false);
const onScroll = () => { scrolled.value = window.scrollY > 4; };

function onKey (event) {
  if (event.key === 'Escape') showCaseManager.value = false;
}

onMounted(() => {
  window.addEventListener('hashchange', onHashChange);
  window.addEventListener('scroll', onScroll, { passive: true });
  document.addEventListener('keydown', onKey);
});
onUnmounted(() => {
  window.removeEventListener('hashchange', onHashChange);
  window.removeEventListener('scroll', onScroll);
  document.removeEventListener('keydown', onKey);
});
</script>

<style scoped>
/* ---------- Navigation Rail ---------- */
.rail {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 40;
  display: none;
  width: 88px;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 16px 0;
  background: var(--md-surface-container);
}
@media (min-width: 1024px) {
  .rail { display: flex; }
}
.rail-brand { display: grid; place-items: center; margin-bottom: 4px; }
.brand-mark {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--md-primary), var(--md-tertiary));
  color: var(--md-on-primary);
  box-shadow: var(--md-elevation-1);
  transition: border-radius var(--md-duration-medium) var(--md-ease-emphasized),
    transform var(--md-duration-medium) var(--md-ease-spring);
}
.rail-brand:hover .brand-mark { border-radius: 24px; transform: rotate(-8deg) scale(1.04); }
.brand-mark-sm { width: 36px; height: 36px; border-radius: 12px; }
.rail-fab { margin-bottom: 12px; }

/* 导航项：图标外面一颗药丸形指示器，激活时从中间横向展开 */
.nav-item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 88px;
  padding: 4px 0 8px;
  color: var(--md-on-surface-variant);
  text-decoration: none;
  -webkit-tap-highlight-color: transparent;
  overflow: visible !important;   /* 水波纹只在药丸里显示，不裁剪整项 */
}
.nav-pill {
  position: relative;
  display: grid;
  place-items: center;
  width: 56px;
  height: 32px;
  border-radius: 9999px;
  isolation: isolate;
  overflow: hidden;
}
.nav-pill::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--md-secondary-container);
  transform: scaleX(0.35);
  opacity: 0;
  z-index: -1;
  transition: transform var(--md-duration-medium) var(--md-ease-spring),
    opacity var(--md-duration-short) var(--md-ease-standard);
}
.nav-pill::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: currentColor;
  opacity: 0;
  z-index: -1;
  transition: opacity var(--md-duration-short);
}
.nav-item:hover .nav-pill::after { opacity: 0.08; }
.nav-item.is-active { color: var(--md-on-surface); }
.nav-item.is-active .nav-pill { color: var(--md-on-secondary-container); }
.nav-item.is-active .nav-pill::before { transform: scaleX(1); opacity: 1; }
.nav-label {
  font-size: 12px;
  line-height: 16px;
  font-weight: 500;
  letter-spacing: 0.04em;
  transition: font-weight var(--md-duration-short);
}
.nav-item.is-active .nav-label { font-weight: 700; }

/* ---------- Top App Bar ---------- */
.top-bar {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 72px;
  padding: 0 16px 0 20px;
  background: var(--md-surface);
  transition: background-color var(--md-duration-medium) var(--md-ease-standard);
}
@media (min-width: 1024px) {
  .top-bar { padding: 0 24px 0 32px; }
}
.top-bar.is-scrolled { background: var(--md-surface-container); }

/* ---------- Navigation Bar（移动端） ---------- */
.bottom-bar {
  position: fixed;
  inset: auto 0 0 0;
  z-index: 40;
  display: flex;
  justify-content: space-around;
  height: 80px;
  padding: 12px 0 16px;
  background: var(--md-surface-container);
}
.bottom-bar .nav-item { width: auto; flex: 1; padding: 0; }
/* 组件样式里写了 display，Tailwind 的 lg:hidden 盖不过，所以在这里按断点隐藏 */
@media (min-width: 1024px) {
  .bottom-bar, .mobile-only { display: none; }
}
.bottom-bar .nav-pill { width: 64px; }

/* 标题切换、图标切换的小动效 */
.title-swap-enter-active { transition: opacity 200ms var(--md-ease-emphasized-decelerate), transform 300ms var(--md-ease-emphasized-decelerate); }
.title-swap-leave-active { transition: opacity 100ms var(--md-ease-emphasized-accelerate); }
.title-swap-enter-from { opacity: 0; transform: translateY(6px); }
.title-swap-leave-to { opacity: 0; }
.icon-spin-enter-active { transition: transform 360ms var(--md-ease-spring), opacity 200ms; }
.icon-spin-leave-active { transition: transform 150ms var(--md-ease-emphasized-accelerate), opacity 150ms; }
.icon-spin-enter-from { transform: rotate(-90deg) scale(0.6); opacity: 0; }
.icon-spin-leave-to { transform: rotate(90deg) scale(0.6); opacity: 0; }
</style>
