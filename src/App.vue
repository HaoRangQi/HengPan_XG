<template>
  <div class="min-h-screen bg-background text-foreground">
    <!-- 参数帮助管理器：各页面的参数说明弹窗共用这一个实例 -->
    <ParameterHelpManager />

    <header class="sticky top-0 z-30 border-b border-border bg-card">
      <div class="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:gap-8 sm:px-6 lg:px-8">
        <a href="#/" class="shrink-0 font-semibold">平台期扫描工具</a>

        <nav class="-mx-1 flex min-w-0 flex-1 items-center gap-1 overflow-x-auto" aria-label="主导航">
          <a v-for="item in navItems" :key="item.path" :href="`#${item.path}`"
            :aria-current="item.path === currentPath ? 'page' : undefined"
            :class="['nav-link', item.path === currentPath && 'is-active']">
            {{ item.label }}
          </a>
          <button type="button" class="nav-link" @click="showCaseManager = true">案例管理</button>
        </nav>

        <ThemeToggle class="shrink-0" />
      </div>
    </header>

    <!-- KeepAlive：切换页面时保留扫描进度和结果 -->
    <KeepAlive>
      <component :is="routes[currentPath].component" />
    </KeepAlive>

    <!-- 案例管理弹窗 -->
    <div v-if="showCaseManager"
      class="fixed inset-0 z-50 flex items-center justify-center overflow-auto bg-black/50 p-4">
      <div class="flex h-[90vh] w-full max-w-6xl flex-col rounded-lg bg-background shadow-xl">
        <div class="flex-1 overflow-auto">
          <CaseManager @close="showCaseManager = false" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, provide, watch, nextTick } from 'vue';
import { ParameterHelpManager } from './components/parameter-help';
import CaseManager from './components/case-management/CaseManager.vue';
import ThemeToggle from './components/ThemeToggle.vue';
import ScanView from './views/ScanView.vue';
import LegacyScanView from './views/LegacyScanView.vue';
import DataView from './views/DataView.vue';
import ApiDocsView from './views/ApiDocsView.vue';
import HengpanScanView from './hengpan/HengpanScanView.vue';

// 用 hash 做页面切换，不需要服务端配合，也不必引入 vue-router
const routes = {
  '/': { label: '横盘选股', component: HengpanScanView },
  '/platform': { label: '平台扫描', component: ScanView },
  '/legacy': { label: '旧版扫描', component: LegacyScanView },
  '/data': { label: '数据管理', component: DataView },
  '/api-docs': { label: '接口文档', component: ApiDocsView },
};
const navItems = Object.entries(routes).map(([path, route]) => ({ path, label: route.label }));

const parsePath = () => {
  const path = window.location.hash.replace(/^#/, '') || '/';
  // `/hengpan` was the original deep link. Keep old bookmarks pointed at the
  // new default page without exposing a duplicate navigation item.
  if (path === '/hengpan') return '/';
  return routes[path] ? path : '/';
};
const currentPath = ref(parsePath());
const onHashChange = () => {
  currentPath.value = parsePath();
  window.scrollTo(0, 0);
};

watch(currentPath, (path) => {
  document.title = `${routes[path].label} · 平台期扫描工具`;
  // KeepAlive 页面重新挂回文档后，让其中的图表按当前尺寸重绘
  nextTick(() => window.dispatchEvent(new Event('resize')));
}, { immediate: true });

const showCaseManager = ref(false);

// 主题状态放在外壳，所有页面共用
const isDarkMode = ref(false);
function toggleDarkMode () {
  isDarkMode.value = !isDarkMode.value;
  document.documentElement.classList.toggle('dark', isDarkMode.value);
  localStorage.setItem('theme', isDarkMode.value ? 'dark' : 'light');
}
provide('isDarkMode', isDarkMode);
provide('toggleDarkMode', toggleDarkMode);

onMounted(() => {
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    isDarkMode.value = true;
    document.documentElement.classList.add('dark');
  }
  window.addEventListener('hashchange', onHashChange);
});

onUnmounted(() => {
  window.removeEventListener('hashchange', onHashChange);
});
</script>

<style scoped>
.nav-link {
  @apply shrink-0 whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors duration-150;
}

.nav-link:hover {
  @apply bg-foreground/5 text-foreground;
}

.nav-link.is-active {
  @apply bg-foreground/[0.08] font-medium text-foreground;
}

.nav-link:focus-visible {
  @apply outline-none ring-2 ring-ring;
}
</style>
