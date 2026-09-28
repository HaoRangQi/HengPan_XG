<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <FullKlineChart v-model:visible="showFullChart" :title="chartStock ? `${chartStock.name}（${chartStock.code}）` : ''"
      :klineData="chartStock?.kline_data || []" :markLines="chartStock?.mark_lines || []" :isDarkMode="isDarkMode" />

    <section class="hero rise-in" aria-label="页面说明">
      <div class="relative z-10 min-w-0 flex-1">
        <p class="flex items-center gap-2 text-label-l opacity-80"><MIcon name="currency_bitcoin" :size="18" />本地加密平台扫描</p>
        <h2 class="mt-2 text-headline-m">找出正在横盘整理的加密交易对</h2>
        <p class="mt-2 max-w-2xl text-body-m opacity-85">读取本地 60 分钟行情，按加密永续和 TradFi 永续分别使用适配阈值。</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <span class="hero-chip"><MIcon name="database" :size="16" />只读本地库</span>
          <span class="hero-chip"><MIcon name="schedule" :size="16" />60 分钟 K 线</span>
          <span class="hero-chip"><MIcon name="token" :size="16" />{{ selectedCategories.length }} 个类别</span>
        </div>
      </div>
    </section>

    <section class="card mt-6 divide-y divide-md-outline-variant overflow-hidden" aria-label="扫描设置">
      <div class="p-5 sm:p-6">
        <h2 class="section-title"><span class="section-icon"><MIcon name="tune" :size="20" /></span>扫描条件</h2>
        <div class="mt-4 grid gap-5 md:grid-cols-2">
          <div>
            <span class="mb-1 block text-sm font-medium">扫描类别</span>
            <div class="mt-2 flex flex-wrap gap-2" role="group" aria-label="扫描类别">
              <button v-for="item in CATEGORY_OPTIONS" :key="item.key" type="button" class="chip"
                :class="config.categories.includes(item.key) && 'is-selected'"
                :aria-pressed="config.categories.includes(item.key)" :disabled="isScanning"
                @click="toggleCategory(item.key)">
                <MIcon v-if="config.categories.includes(item.key)" name="check" />{{ item.label }}
              </button>
            </div>
            <p class="mt-1.5 text-xs text-muted-foreground">默认两类全选；类别参数分开计算，避免低波动 TradFi 淹没加密永续。</p>
          </div>
          <div>
            <label for="crypto-symbols" class="mb-1 block text-sm font-medium">交易对（可选）</label>
            <input id="crypto-symbols" v-model.trim="config.symbolInput" class="input" type="text"
              placeholder="留空扫描全部，例如 BTCUSDT,ETHUSDT" :disabled="isScanning">
            <p class="mt-1.5 text-xs text-muted-foreground">留空扫描所选类别的全部本地交易对；可用英文逗号分隔。</p>
          </div>
        </div>

        <div class="mt-5">
          <label class="mb-1 block text-sm font-medium">窗口期</label>
          <div class="seg" role="group" aria-label="窗口期预设">
            <button v-for="preset in WINDOW_PRESETS" :key="preset.value" type="button" class="seg-btn"
              :class="config.windowsInput === preset.value && 'is-active'" :aria-pressed="config.windowsInput === preset.value"
              :disabled="isScanning" @click="config.windowsInput = preset.value">{{ preset.label }}</button>
            <button type="button" class="seg-btn" :class="customWindowsOpen && 'is-active'"
              :disabled="isScanning" @click="customWindowsOpen = true">自定义</button>
          </div>
          <div v-if="customWindowsOpen" class="mt-2 flex max-w-sm gap-2">
            <input v-model="customWindows" class="input" type="text" inputmode="numeric" placeholder="例如 40,80,120">
            <button type="button" class="btn-quiet h-10 px-4" @click="applyWindows">确定</button>
          </div>
          <p class="mt-1.5 text-xs text-muted-foreground">当前：<span class="font-medium text-foreground">{{ windows.join('、') }}</span> 根 K 线，每个窗口单独判断</p>
          <p v-if="formError" class="mt-1.5 text-xs text-destructive" role="alert">{{ formError }}</p>
        </div>
      </div>

      <div class="p-5 sm:p-6">
        <div class="flex items-baseline justify-between gap-4">
          <h2 class="section-title">类别参数</h2>
          <span class="text-xs text-muted-foreground">按交易对类别自动套用</span>
        </div>
        <div class="mt-4 grid gap-5 lg:grid-cols-2">
          <div v-for="category in selectedCategories" :key="category" class="rounded-md border border-border p-4">
            <h3 class="text-sm font-semibold">{{ categoryLabel(category) }}</h3>
            <div class="mt-3 grid gap-4 sm:grid-cols-3">
              <label v-for="key in PARAM_KEYS" :key="key" class="block text-xs">
                <span class="mb-1 block text-muted-foreground">{{ PARAM_LABELS[key] }}</span>
                <input v-model.number="config.categoryParams[category][key]" class="input h-9" type="number" step="0.001" min="0.0001" max="1" :disabled="isScanning">
              </label>
            </div>
          </div>
        </div>
        <div class="mt-5 flex flex-wrap gap-5 text-sm">
          <label class="flex items-center gap-2"><input v-model="config.useBoxDetection" type="checkbox" :disabled="isScanning"> 箱体质量检测</label>
          <label class="flex items-center gap-2"><input v-model="config.useVolumeAnalysis" type="checkbox" :disabled="isScanning"> 成交量分析</label>
        </div>
      </div>

      <div class="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <p class="min-w-0 text-sm text-muted-foreground">{{ summaryText }}</p>
        <button type="button" class="btn btn-filled btn-lg shrink-0" :disabled="isScanning" @click="startScan">
          <MIcon :name="isScanning ? 'progress_activity' : 'play_arrow'" :class="isScanning && 'animate-spin'" />
          {{ isScanning ? '扫描中…' : '开始扫描' }}
        </button>
      </div>
    </section>

    <section ref="resultsRef" class="card mt-6 scroll-mt-24 overflow-hidden" aria-label="扫描结果">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4 sm:px-6">
        <div><h2 class="section-title">扫描结果</h2><p v-if="results.length" class="mt-1 text-xs text-muted-foreground">已发现 {{ results.length }} 个交易对</p></div>
        <div class="flex items-center gap-2">
          <label for="crypto-history" class="text-xs text-muted-foreground">历史结果</label>
          <select id="crypto-history" v-model="selectedHistoryId" class="select h-8 max-w-[18rem] text-xs" :disabled="isScanning" @change="loadHistory">
            <option value="">选择历史扫描…</option>
            <option v-for="item in histories" :key="item.history_id" :value="item.history_id">{{ historyLabel(item) }}</option>
          </select>
        </div>
      </div>
      <div v-if="scan.status === 'running'" class="px-5 py-8 sm:px-6">
        <div class="flex items-baseline justify-between"><p class="text-sm font-medium">正在扫描本地行情</p><span class="text-sm tabular-nums">{{ scan.progress }}%</span></div>
        <div class="mt-3 h-2 overflow-hidden rounded-full bg-foreground/[0.08]"><div class="h-full rounded-full bg-primary transition-transform" :style="{ transform: `scaleX(${scan.progress / 100})`, transformOrigin: 'left' }"></div></div>
        <p class="mt-3 text-sm" aria-live="polite">{{ scan.message }}</p>
        <button type="button" class="btn-quiet mt-3 h-8 px-4 text-xs" :disabled="cancelRequested" @click="cancelScan">{{ cancelRequested ? '正在停止…' : '停止扫描' }}</button>
      </div>
      <div v-else-if="scan.status === 'failed'" class="px-5 py-8" role="alert"><p class="text-sm text-destructive">{{ scan.message }}</p><details v-if="scan.error" class="mt-3"><summary class="cursor-pointer text-xs">错误详情</summary><pre class="mt-2 overflow-auto text-xs">{{ scan.error }}</pre></details></div>
      <div v-else-if="!results.length" class="px-5 py-12 text-center"><p class="text-sm font-medium">{{ scan.status === 'idle' ? '还没有扫描结果' : '没有找到符合条件的交易对' }}</p><p class="mt-1 text-sm text-muted-foreground">请先在数据管理页同步本地加密行情。</p></div>
      <template v-else>
        <div class="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3 sm:px-6">
          <input v-model.trim="keyword" class="input h-9 w-full sm:w-64" type="search" placeholder="搜索交易对" aria-label="搜索交易对">
          <select v-model="categoryFilter" class="select" aria-label="按类别筛选"><option value="">全部类别</option><option v-for="item in CATEGORY_OPTIONS" :key="item.key" :value="item.key">{{ item.label }}</option></select>
        </div>
        <div class="grid gap-4 p-4 sm:p-6 lg:grid-cols-2">
          <article v-for="item in filteredResults" :key="resultKey(item)" class="flex flex-col rounded-lg border border-border">
            <header class="flex items-start justify-between gap-3 px-4 pt-3"><div class="min-w-0"><div class="flex items-baseline gap-2"><h3 class="truncate text-base font-semibold">{{ item.name }}</h3><span class="font-mono text-xs text-muted-foreground">{{ item.code }}</span></div><span class="chip mt-1">{{ item.category_label }}</span></div><button type="button" class="btn-quiet h-8 px-2.5" @click="openChart(item)"><MIcon name="open_in_full" :size="17" />大图</button></header>
            <KlineChart :klineData="item.kline_data" :markLines="item.mark_lines || []" :isDarkMode="isDarkMode" height="200px" width="100%" class="mt-1" />
            <dl class="grid grid-cols-2 gap-x-4 gap-y-2 px-4 pb-4 pt-1 text-xs"><div><dt class="text-muted-foreground">命中窗口</dt><dd class="mt-0.5 font-medium">{{ item.platform_windows.join('、') }} 根</dd></div><div><dt class="text-muted-foreground">最新价</dt><dd class="mt-0.5 font-medium">{{ item.last_price ?? '—' }}</dd></div><div class="col-span-2"><dt class="text-muted-foreground">平台理由</dt><dd class="mt-0.5 text-muted-foreground">{{ Object.values(item.selection_reasons || {}).join('；') || '满足平台期条件' }}</dd></div></dl>
          </article>
        </div>
      </template>
    </section>
  </main>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue';
import axios from 'axios';
import KlineChart from '../components/KlineChart.vue';
import FullKlineChart from '../components/FullKlineChart.vue';
import MIcon from '../ui/MIcon.vue';

const isDarkMode = inject('isDarkMode');
const CATEGORY_OPTIONS = [{ key: 'perpetual', label: '加密永续' }, { key: 'tradifi', label: 'TradFi 永续' }];
const PARAM_KEYS = ['box_threshold', 'ma_diff_threshold', 'volatility_threshold'];
const PARAM_LABELS = { box_threshold: '振幅阈值', ma_diff_threshold: '均线粘合度', volatility_threshold: '波动率阈值' };
const DEFAULT_PARAMS = { perpetual: { box_threshold: 0.15, ma_diff_threshold: 0.01, volatility_threshold: 0.017 }, tradifi: { box_threshold: 0.04, ma_diff_threshold: 0.003, volatility_threshold: 0.004 } };
const WINDOW_PRESETS = [{ label: '标准 40、80、120', value: '40,80,120' }, { label: '短期 20、40、60', value: '20,40,60' }, { label: '中期 60、120、180', value: '60,120,180' }];
const config = reactive({ categories: ['perpetual', 'tradifi'], symbolInput: '', windowsInput: '40,80,120', categoryParams: structuredClone(DEFAULT_PARAMS), useBoxDetection: true, useVolumeAnalysis: false });
const selectedCategories = computed(() => config.categories);
const windows = computed(() => [...new Set(config.windowsInput.split(/[,，\s]+/).map(Number).filter(Number.isInteger))]);
const categoryLabel = key => CATEGORY_OPTIONS.find(item => item.key === key)?.label || key;
const toggleCategory = key => { config.categories = config.categories.includes(key) ? config.categories.filter(item => item !== key) : [...config.categories, key]; };
const customWindowsOpen = ref(false); const customWindows = ref(''); const formError = ref('');
function applyWindows () { const parsed = customWindows.value.split(/[,，\s]+/).map(Number).filter(n => Number.isInteger(n) && n >= 10); if (!parsed.length) { formError.value = '请输入 10 以上的整数窗口期'; return; } config.windowsInput = [...new Set(parsed)].join(','); customWindowsOpen.value = false; formError.value = ''; }
const summaryText = computed(() => `${config.categories.length} 个类别 · ${windows.value.join('、')} 根 K 线 · 本地数据，不联网`);

const scan = reactive({ status: 'idle', progress: 0, message: '', error: '', scanned: 0, total: 0 });
const results = ref([]); const histories = ref([]); const selectedHistoryId = ref(''); const currentTaskId = ref(null); const cancelRequested = ref(false); const keyword = ref(''); const categoryFilter = ref(''); const resultsRef = ref(null); let pollTimer = null; let streamCursor = 0;
const isScanning = computed(() => scan.status === 'running');
const filteredResults = computed(() => results.value.filter(item => (!categoryFilter.value || item.category === categoryFilter.value) && (!keyword.value || item.code.toLowerCase().includes(keyword.value.toLowerCase()) || item.name.toLowerCase().includes(keyword.value.toLowerCase()))));
function resultKey (item) { return `${item?.category || ''}:${item?.code || ''}`; }
function appendResults (items) { if (!Array.isArray(items)) return; const seen = new Set(results.value.map(resultKey)); items.filter(item => item?.code && !seen.has(resultKey(item))).forEach(item => { results.value.push(item); seen.add(resultKey(item)); }); }
function stopPolling () { clearInterval(pollTimer); pollTimer = null; }
async function poll (taskId) { try { const { data } = await axios.get(`/api/crypto/platform/scan/status/${taskId}?since=${streamCursor}`); Object.assign(scan, { status: data.status, progress: data.progress || 0, message: data.message || '', error: data.error || '', scanned: data.scanned || 0, total: data.total || 0 }); appendResults(data.new_results); streamCursor = data.cursor || streamCursor; if (['completed', 'cancelled', 'failed'].includes(data.status)) { if (data.result) { results.value = []; appendResults(data.result); } stopPolling(); cancelRequested.value = false; await loadHistories(); } } catch (error) { if (error.response?.status === 404) { stopPolling(); scan.status = 'failed'; scan.message = '扫描任务已丢失，请重新扫描'; } } }
function buildPayload () { const symbols = config.symbolInput.split(/[,，\s]+/).map(value => value.trim()).filter(Boolean); return { categories: config.categories, symbols: symbols.length ? symbols : null, windows: windows.value, category_params: Object.fromEntries(config.categories.map(category => [category, config.categoryParams[category]])), use_box_detection: config.useBoxDetection, use_volume_analysis: config.useVolumeAnalysis }; }
async function startScan () { if (isScanning.value) return; if (!config.categories.length) { formError.value = '至少选择一个扫描类别'; return; } if (!windows.value.length) { formError.value = '请至少设置一个窗口期'; return; } formError.value = ''; results.value = []; streamCursor = 0; cancelRequested.value = false; Object.assign(scan, { status: 'running', progress: 0, message: '正在提交本地扫描任务…', error: '', scanned: 0, total: 0 }); nextTick(() => resultsRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })); try { const { data } = await axios.post('/api/crypto/platform/scan/start', buildPayload()); currentTaskId.value = data.task_id; scan.message = data.message; pollTimer = setInterval(() => poll(data.task_id), 1500); } catch (error) { const detail = error.response?.data?.detail; scan.status = 'failed'; scan.message = `扫描任务提交失败：${Array.isArray(detail) ? detail.map(item => item.msg).join('；') : (detail || '请求参数不合法，请检查输入')}`; } }
async function cancelScan () { if (!currentTaskId.value || !isScanning.value) return; cancelRequested.value = true; await axios.post(`/api/crypto/platform/scan/cancel/${currentTaskId.value}`); }
function historyLabel (item) { return `${new Date((item.saved_at || 0) * 1000).toLocaleString()} · ${item.result_count || 0} 个 · ${item.categories?.map(categoryLabel).join('、') || ''}`; }
async function loadHistories () { try { const { data } = await axios.get('/api/crypto/platform/scan/history'); histories.value = data.histories || []; } catch { histories.value = []; } }
async function loadHistory () { if (!selectedHistoryId.value) return; const { data } = await axios.get(`/api/crypto/platform/scan/history/${selectedHistoryId.value}`); results.value = data.results || []; Object.assign(scan, { status: data.status || 'completed', progress: 100, scanned: data.scanned || 0, total: data.total || 0, message: `已加载历史扫描：${results.value.length} 个` }); }
const showFullChart = ref(false); const chartStock = ref(null); const openChart = item => { chartStock.value = item; showFullChart.value = true; };
onMounted(loadHistories); onUnmounted(stopPolling);
</script>
