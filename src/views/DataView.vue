<template>
  <main class="mx-auto max-w-[1440px] px-4 pb-10 sm:px-6 lg:px-8">
    <!-- 主标签：A 股和加密货币各自独立，数据互不混杂 -->
    <div class="tab-bar sticky top-[72px] z-20 -mx-4 mb-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8"
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
      <div class="period-bar mb-6">
        <span class="period-label">
          <MIcon name="schedule" :size="18" />
          周期
        </span>
        <div class="segmented period-options" role="tablist" aria-label="行情周期">
          <button v-for="period in PERIODS" :key="period.key" type="button" role="tab"
            :class="activePeriods.ashare === period.key && 'is-selected'"
            :aria-selected="activePeriods.ashare === period.key" :disabled="period.disabled"
            :title="period.disabled ? `${period.label}暂不可用` : ''"
            @click="activePeriods.ashare = period.key">
            {{ period.label }}
          </button>
        </div>
      </div>

      <div v-show="activePeriods.ashare === '60'">
        <LocalStorePanel :market="ASHARE" :active="visited.ashare" />
      </div>
      <section v-show="activePeriods.ashare === 'daily'" class="period-empty" aria-live="polite">
        <span class="empty-icon"><MIcon name="calendar_month" :size="28" /></span>
        <p class="mt-3 text-title-m">本地 A 股日线行情尚未接入</p>
        <p class="mt-1 text-body-m text-md-on-surface-variant">当前数据管理仅提供 60 分钟行情。</p>
      </section>
    </div>
    <div v-show="active === 'crypto'" role="tabpanel">
      <div class="period-bar mb-6">
        <span class="period-label">
          <MIcon name="schedule" :size="18" />
          周期
        </span>
        <div class="segmented period-options" role="tablist" aria-label="行情周期">
          <button v-for="period in PERIODS" :key="period.key" type="button" role="tab"
            :class="activePeriods.crypto === period.key && 'is-selected'"
            :aria-selected="activePeriods.crypto === period.key" :disabled="period.disabled"
            :title="period.disabled ? `${period.label}暂不可用` : ''"
            @click="activePeriods.crypto = period.key">
            {{ period.label }}
          </button>
        </div>
      </div>

      <div v-show="activePeriods.crypto === '60'">
        <LocalStorePanel :market="CRYPTO" :active="visited.crypto" />
      </div>
      <section v-show="activePeriods.crypto === 'daily'" class="period-empty" aria-live="polite">
        <span class="empty-icon"><MIcon name="calendar_month" :size="28" /></span>
        <p class="mt-3 text-title-m">本地加密货币日线行情尚未接入</p>
        <p class="mt-1 text-body-m text-md-on-surface-variant">当前数据管理仅提供 60 分钟行情。</p>
      </section>
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
const PERIODS = [
  { key: 'daily', label: '日线' },
  { key: '60', label: '60 分钟' },
  { key: '5', label: '5 分钟', disabled: true },
];
const STORAGE_KEY = 'data-view-tab';

const saved = localStorage.getItem(STORAGE_KEY);
const active = ref(TABS.some((t) => t.key === saved) ? saved : 'ashare');
const activePeriods = reactive({ ashare: '60', crypto: '60' });
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

.period-bar {
  display: flex;
  min-height: 48px;
  align-items: center;
  justify-content: center;
  gap: 16px;
  border-bottom: 1px solid var(--md-outline-variant);
  padding-bottom: 16px;
}
.period-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--md-on-surface-variant);
  font-size: 13px;
  font-weight: 500;
}
.period-options { height: 40px; }
.period-options > button {
  min-width: 96px;
  padding: 0 18px;
}
.period-empty {
  display: flex;
  min-height: 360px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

@media (max-width: 520px) {
  .period-bar {
    align-items: stretch;
    flex-direction: column;
    gap: 8px;
  }
  .period-options { width: 100%; }
  .period-options > button {
    min-width: 0;
    flex: 1;
    padding: 0 8px;
  }
}
</style>
