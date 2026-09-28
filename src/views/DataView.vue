<template>
  <main class="mx-auto max-w-[1440px] px-4 pb-10 sm:px-6 lg:px-8">
    <!-- 主标签：A 股和加密货币各自独立，数据互不混杂 -->
    <div class="tab-bar sticky top-[72px] z-20 -mx-4 mb-6 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
      :class="scrolled && 'is-scrolled'">
      <div ref="tabsRef" class="tabs" role="tablist" aria-label="数据分类">
        <button v-for="tab in TABS" :key="tab.key" :ref="(el) => (tabRefs[tab.key] = el)" type="button" role="tab"
          class="tab" :class="active === tab.key && 'is-active'" :aria-selected="active === tab.key"
          @click="activate(tab.key)">
          <MIcon :name="tab.icon" :filled="active === tab.key" :size="20" />
          {{ tab.label }}
          <span v-if="tab.badge" class="badge badge-tertiary">{{ tab.badge }}</span>
        </button>
        <span class="tab-indicator" :style="indicator"></span>
      </div>
    </div>

    <!-- v-show 保留每个标签的状态（查询条件、滚动位置、同步进度），切回来不重载 -->
    <div v-show="active === 'ashare'" role="tabpanel">
      <LocalStorePanel :market="ASHARE" :active="visited.ashare" />
    </div>
    <div v-show="active === 'crypto'" role="tabpanel">
      <LocalStorePanel :market="CRYPTO" :active="visited.crypto" />
    </div>
    <div v-show="active === 'sources'" role="tabpanel">
      <SourceDocsPanel :active="visited.sources" />
    </div>
  </main>
</template>

<script setup>
import { nextTick, onActivated, onDeactivated, onMounted, onUnmounted, reactive, ref } from 'vue';
import MIcon from '../ui/MIcon.vue';
import LocalStorePanel from './data/LocalStorePanel.vue';
import SourceDocsPanel from './data/SourceDocsPanel.vue';
import { ASHARE, CRYPTO } from './data/markets.js';

const TABS = [
  { key: 'ashare', label: 'A 股行情', icon: 'candlestick_chart' },
  { key: 'crypto', label: '加密货币', icon: 'currency_bitcoin', badge: '新' },
  { key: 'sources', label: '数据源', icon: 'hub' },
];
const STORAGE_KEY = 'data-view-tab';

const saved = localStorage.getItem(STORAGE_KEY);
const active = ref(TABS.some((t) => t.key === saved) ? saved : 'ashare');
const visited = reactive({ ashare: false, crypto: false, sources: false, [active.value]: true });

const tabsRef = ref(null);
const tabRefs = {};
const indicator = reactive({ width: '0px', transform: 'translateX(0)' });

// 下划线指示器滑到当前标签下面，宽度跟随标签文字
function moveIndicator () {
  const el = tabRefs[active.value];
  if (!el) return;
  const inset = 12;
  indicator.width = `${el.offsetWidth - inset * 2}px`;
  indicator.transform = `translateX(${el.offsetLeft + inset}px)`;
}

function activate (key) {
  active.value = key;
  visited[key] = true;
  localStorage.setItem(STORAGE_KEY, key);
  nextTick(moveIndicator);
}

// 标签栏吸顶后和 Top App Bar 一起加深底色，看起来是同一块
const scrolled = ref(false);
const onScroll = () => { scrolled.value = window.scrollY > 4; };

onMounted(() => {
  nextTick(moveIndicator);
  // 字体加载完成后标签宽度会变，再校准一次
  document.fonts?.ready.then(moveIndicator);
  window.addEventListener('resize', moveIndicator);
  window.addEventListener('scroll', onScroll, { passive: true });
});
onActivated(() => { nextTick(moveIndicator); onScroll(); });
onDeactivated(() => { scrolled.value = false; });
onUnmounted(() => {
  window.removeEventListener('resize', moveIndicator);
  window.removeEventListener('scroll', onScroll);
});
</script>

<style scoped>
.tab-bar {
  background: var(--md-surface);
  transition: background-color var(--md-duration-medium) var(--md-ease-standard);
}
.tab-bar.is-scrolled { background: var(--md-surface-container); }
</style>
