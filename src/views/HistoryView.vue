<template>
  <main class="history-page mx-auto max-w-[1440px] px-8 pb-10">
    <FullKlineChart v-model:visible="chart.visible" :title="chart.title" :kline-data="chart.rows"
      :mark-lines="chart.marks" :is-dark-mode="isDarkMode" />

    <div class="flex flex-wrap items-center justify-between gap-3 py-4">
      <div class="segmented" aria-label="历史市场">
        <button v-for="market in markets" :key="market.key" type="button"
          :class="filters.market === market.key && 'is-active'" :aria-pressed="filters.market === market.key"
          @click="switchMarket(market.key)">{{ market.label }}</button>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <a :href="`#${HISTORY_KINDS[filters.kind || (filters.market === 'a' ? 'hengpan_a' : 'hengpan_u')].path}`"
          class="btn btn-text px-3 py-2"><MIcon name="radar" :size="18" />去扫描</a>
        <button class="btn btn-text px-3 py-2" type="button" :disabled="loading || busy" @click="refresh">
          <MIcon name="refresh" :size="18" />刷新</button>
        <button class="btn btn-text px-3 py-2" type="button" :aria-expanded="showCleanup" @click="showCleanup = !showCleanup">
          <MIcon name="delete_sweep" :size="18" />清理历史</button>
      </div>
    </div>
    <p class="mb-4 text-sm text-muted-foreground">扫描结束后自动归档。按标的合并展示，保留每次扫描与当时的 K 线，不覆盖重扫记录。</p>
    <p v-if="overview" class="mb-4 text-sm text-muted-foreground">
      全部历史 {{ overview.runs }} 次 · K 线快照 {{ formatBytes(overview.kline_bytes) }}
      <span v-if="needsCleanup" class="ml-2 font-medium text-foreground">建议清理：{{ overview.kline_bytes >= 500 * 1024 * 1024 ? '快照已超过 500 MiB' : '存在超过 30 天的记录' }}。置顶记录受保护。</span>
    </p>

    <section v-if="showCleanup" class="mb-5 rounded-xl border border-border bg-card p-4" aria-label="历史清理">
      <h2 class="text-base font-medium">清理旧扫描与对应 K 线</h2>
      <p class="mt-1 text-sm text-muted-foreground">先预览删除数量，再确认执行；置顶记录不会被批量清理。按体积清理时，置顶记录仍占容量。</p>
      <form class="mt-3 flex flex-wrap items-end gap-3" @submit.prevent="cleanup">
        <label class="history-field">清理范围<select v-model="cleanupForm.kind" class="input">
          <option value="">全部市场、全部类型</option>
          <option v-for="(kind, key) in HISTORY_KINDS" :key="key" :value="key">{{ kind.label }}</option>
        </select></label>
        <label class="history-field">保留策略<select v-model="cleanupForm.mode" class="input">
          <option value="days">最近 N 天</option><option value="count">最新 N 条（不含置顶）</option><option value="size">K 线容量上限（MiB）</option>
        </select></label>
        <label class="history-field">保留值<input v-model.number="cleanupForm.value" class="input w-28" type="number" min="1" required></label>
        <button class="btn btn-danger" type="submit" :disabled="busy">预览清理</button>
      </form>
    </section>

    <form class="flex flex-wrap items-end gap-3 border-y border-border py-4" aria-label="历史筛选" @submit.prevent="applyFilters">
      <label class="history-field">周期<select v-model="filters.period" class="input">
        <option value="intraday">日内（60 分钟 / 1 小时）</option><option value="d">日线</option><option value="all">全部周期</option>
      </select></label>
      <label class="history-field">扫描类型<select v-model="filters.kind" class="input">
        <option value="">全部类型</option><option v-for="(kind, key) in availableKinds" :key="key" :value="key">{{ kind.label }}</option>
      </select></label>
      <label class="history-field">状态<select v-model="filters.status" class="input">
        <option value="">全部状态</option><option value="completed">完成</option><option value="cancelled">已停止</option><option value="failed">失败</option>
      </select></label>
      <label class="history-field">起始扫描日<input v-model="filters.date_from" class="input" type="date"></label>
      <label class="history-field">结束扫描日<input v-model="filters.date_to" class="input" type="date"></label>
      <label class="history-field">标的代码<input v-model="filters.code" class="input w-40" type="search" :placeholder="filters.market === 'a' ? 'sh.600519' : 'BTCUSDT'"></label>
      <button class="btn btn-primary" type="submit" :disabled="busy">查询</button>
      <button class="btn btn-text px-3 py-2" type="button" @click="resetFilters">重置</button>
    </form>

    <div class="my-4 flex flex-wrap items-center justify-between gap-3">
      <div class="segmented" aria-label="历史展示方式">
        <button type="button"  :class="filters.view === 'symbols' && 'is-active'"
          :aria-pressed="filters.view === 'symbols'" @click="switchView('symbols')">按标的去重</button>
        <button type="button"  :class="filters.view === 'runs' && 'is-active'"
          :aria-pressed="filters.view === 'runs'" @click="switchView('runs')">扫描记录</button>
      </div>
      <span class="text-sm text-muted-foreground" aria-live="polite">{{ total }} {{ filters.view === 'symbols' ? '个标的' : '次扫描' }}</span>
    </div>
    <p v-if="filters.view === 'symbols'" class="mb-3 text-sm text-muted-foreground">规则数按当前筛选范围内的不同规则参数统计；同参数重扫不重复计数。无结果的失败扫描请切换「扫描记录」查看。</p>
    <div v-if="error" class="my-4 rounded-xl border border-border p-4" role="alert">{{ error }} <button class="btn btn-text px-3" @click="refresh">重试</button></div>
    <section :aria-busy="loading" aria-label="历史列表">
      <p v-if="loading" class="py-10 text-center text-muted-foreground" role="status">正在读取历史…</p>
      <div v-else-if="!rows.length && !error" class="py-12 text-center">
        <MIcon name="history" :size="30" /><p class="mt-3 font-medium">当前筛选下暂无{{ filters.view === 'symbols' ? '命中标的' : '扫描记录' }}</p>
        <p class="mt-2 text-sm text-muted-foreground">可切换周期、放宽扫描日，或先完成一次扫描。</p>
      </div>
      <div v-else-if="rows.length" class="overflow-x-auto rounded-xl border border-border">
        <table class="history-table w-full text-left text-sm">
          <thead><tr v-if="filters.view === 'symbols'"><th>标的</th><th>命中规则</th><th>扫描次数</th><th>最近扫描</th><th>最新收盘价</th><th>操作</th></tr>
            <tr v-else><th>扫描类型 / 保存时间</th><th>扫描日 / 周期</th><th>状态</th><th>入选 / 已扫</th><th>备注</th><th>操作</th></tr></thead>
          <tbody><tr v-for="item in rows" :key="filters.view === 'symbols' ? item.code : item.run_id">
            <template v-if="filters.view === 'symbols'">
              <td><strong>{{ item.name || item.code }}</strong><div class="text-xs text-muted-foreground">{{ item.code }} · {{ item.group_label || '—' }}</div></td>
              <td><span class="badge badge-primary">{{ item.rule_count }} 条规则</span></td><td>{{ item.run_count }} 次</td>
              <td>{{ item.scan_date || '—' }}<div class="text-xs text-muted-foreground">{{ HISTORY_KINDS[item.kind]?.label }} · {{ frequencyLabel(item.frequency) }}</div></td>
              <td class="tabular-nums">{{ price(item.close) }}</td>
              <td><div class="flex gap-2"><button class="btn btn-text" @click="openRun(item.run_id, item.code)">最新详情</button>
                <button class="btn btn-text" @click="showAppearances(item.code)">出现记录</button></div></td>
            </template>
            <template v-else>
              <td><strong>{{ item.kind_label }}</strong><span v-if="item.pinned" class="ml-2 badge">已置顶</span>
                <div class="text-xs text-muted-foreground">{{ timestampLabel(item.saved_at) }}</div>
                <span v-if="item.duplicate_count > 1" class="text-xs text-muted-foreground">同参数 {{ item.duplicate_count }} 次</span></td>
              <td>{{ item.scan_date || '未确定' }}<div class="text-xs text-muted-foreground">{{ frequencyLabel(item.frequency) }}</div></td>
              <td>{{ statusLabel(item.status) }}</td><td>{{ item.result_count }} / {{ item.scanned }}</td>
              <td class="max-w-48 whitespace-pre-wrap break-words">{{ item.note || '—' }}</td>
              <td><div class="flex gap-3"><button class="btn btn-text" @click="openRun(item.run_id)">详情 / 编辑</button>
                <button class="btn btn-text" :disabled="busy" @click="removeRun(item)">删除</button></div></td>
            </template>
          </tr></tbody>
        </table>
      </div>
      <div class="mt-4 flex items-center justify-end gap-4">
        <button class="btn btn-text px-3 py-2" :disabled="page <= 1 || loading" @click="loadPage(page - 1)">上一页</button>
        <span class="text-sm">{{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span>
        <button class="btn btn-text px-3 py-2" :disabled="page * 20 >= total || loading" @click="loadPage(page + 1)">下一页</button>
      </div>
    </section>

    <section v-if="detail || detailLoading" ref="detailSection" class="mt-8 scroll-mt-24 border-t border-border pt-5" aria-label="扫描详情">
      <p v-if="detailLoading" role="status">正在读取扫描详情…</p>
      <template v-else-if="detail">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-lg font-medium">{{ detail.kind_label }} · {{ detail.scan_date || '扫描日未确定' }} · {{ frequencyLabel(detail.frequency) }}</h2>
          <button class="btn btn-text px-3 py-2" @click="closeDetail">收起详情</button>
        </div>
        <p class="mt-2 text-sm">{{ statusLabel(detail.status) }} · {{ detail.message }}</p>
        <p class="mt-1 break-all text-xs text-muted-foreground">记录 ID：{{ detail.run_id }} · 保存于 {{ timestampLabel(detail.saved_at) }} · K 线 {{ formatBytes(detail.kline_bytes) }}</p>
        <form class="my-4 flex flex-wrap items-end gap-3" @submit.prevent="saveNote">
          <label class="history-field min-w-0 flex-1">备注<textarea v-model="note" class="input min-h-20 w-full" maxlength="2000" placeholder="记录本次扫描的观察结论"></textarea></label>
          <button class="btn btn-primary" :disabled="busy" type="submit">保存备注</button>
          <button class="btn btn-text px-3 py-2" type="button" :disabled="busy" @click="togglePinned">{{ detail.pinned ? '取消置顶保护' : '置顶并保护' }}</button>
          <button class="btn btn-text px-3 py-2" type="button" :disabled="busy" @click="removeRun(detail)">删除本次扫描</button>
        </form>
        <details class="my-3"><summary class="cursor-pointer text-sm">扫描参数与统计</summary>
          <pre class="mt-2 max-h-80 overflow-auto rounded-lg bg-card p-3 text-xs">{{ JSON.stringify({ params: detail.params, rules: detail.rules, stats: detail.stats }, null, 2) }}</pre></details>
        <details v-if="detail.error" class="my-3" open><summary class="cursor-pointer text-sm">失败原因</summary>
          <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs">{{ detail.error }}</pre></details>
        <label v-if="detail.results.length" class="history-field my-4 max-w-sm">筛选本次入选标的<input v-model="detailCode" class="input" type="search" placeholder="输入代码或名称"></label>
        <p v-if="!detail.results.length" class="py-6 text-sm text-muted-foreground">本次扫描没有入选标的。</p>
        <div v-for="hit in visibleHits" :key="hitIdentity(hit).code" class="border-b border-border py-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div><strong>{{ hitIdentity(hit).name }}</strong><span class="ml-2 text-sm text-muted-foreground">{{ hitIdentity(hit).code }}</span>
              <span class="ml-3 badge badge-primary">命中 {{ hit.rule_count }} 条规则</span></div>
            <button class="btn btn-text px-3 py-2" :disabled="chartLoading" @click="showChart(hit)">查看 K 线</button>
          </div>
          <details class="mt-2 text-sm"><summary class="cursor-pointer text-muted-foreground">查看命中规则及口径</summary>
            <div v-for="ruleId in hit.matched_rules" :key="ruleId" class="mt-3">
              <div class="flex flex-wrap items-center gap-3"><span>{{ hit.matches ? `规则 ${ruleId}` : `窗口 ${ruleId} 根` }}</span>
                <span v-if="hit.matches">{{ hit.matches[ruleId]?.passed_full ? '整体口径通过' : '仅实体口径通过' }}</span>
                <button class="btn btn-text" :disabled="chartLoading" @click="showChart(hit, ruleId)">按此规则看图</button></div>
              <p v-if="hit.selection_reasons?.[ruleId]" class="mt-1 text-muted-foreground">{{ hit.selection_reasons[ruleId] }}</p>
              <pre v-if="hit.matches" class="mt-2 overflow-auto text-xs">{{ JSON.stringify({ params: detail.rules.find(rule => String(rule.id) === ruleId)?.params, match: hit.matches[ruleId] }, null, 2) }}</pre>
            </div>
          </details>
        </div>
        <p v-if="filteredHits.length > visibleHits.length" class="mt-4"><button class="btn btn-text" @click="hitLimit += 50">再显示 50 个（共 {{ filteredHits.length }} 个）</button></p>
      </template>
    </section>
  </main>
</template>

<script setup>
import { computed, inject, nextTick, onActivated, onDeactivated, reactive, ref } from 'vue';
import axios from 'axios';
import MIcon from '../ui/MIcon.vue';
import FullKlineChart from '../components/FullKlineChart.vue';
import { useFeedback } from '../ui/feedback.js';
import { HISTORY_KINDS, historyQuery, hitIdentity, hitMarks, cleanupPayload, formatBytes,
  frequencyLabel, statusLabel, timestampLabel } from './historyPresentation.js';

const { notify, confirm } = useFeedback();
const isDarkMode = inject('isDarkMode', ref(false));
const markets = [{ key: 'a', label: 'A 股' }, { key: 'crypto', label: '币圈' }];
const defaults = () => ({ market: 'a', view: 'symbols', period: 'intraday', kind: '', status: '', date_from: '', date_to: '', code: '' });
const filters = reactive(defaults());
const availableKinds = computed(() => Object.fromEntries(Object.entries(HISTORY_KINDS).filter(([, kind]) => kind.market === filters.market)));
const rows = ref([]), total = ref(0), page = ref(1), overview = ref(null), loading = ref(false), error = ref(''), busy = ref(false);
const showCleanup = ref(false);
const cleanupForm = reactive({ mode: 'days', value: 30, kind: '' });
const detail = ref(null), detailLoading = ref(false), detailSection = ref(null), detailCode = ref(''), note = ref(''), hitLimit = ref(50);
const chartLoading = ref(false);
const chart = reactive({ visible: false, title: '', rows: [], marks: [] });
let listVersion = 0, detailVersion = 0, chartVersion = 0;
let appliedFilters = { ...filters };
let lastHash = '';
const needsCleanup = computed(() => overview.value && (overview.value.kline_bytes >= 500 * 1024 * 1024 ||
  (overview.value.oldest_saved_at && Date.now() / 1000 - overview.value.oldest_saved_at > 30 * 86400)));
const filteredHits = computed(() => (detail.value?.results || []).filter(hit => {
  const { code, name } = hitIdentity(hit);
  return `${code} ${name}`.toLowerCase().includes(detailCode.value.trim().toLowerCase());
}));
const visibleHits = computed(() => filteredHits.value.slice(0, hitLimit.value));
const price = value => Number.isFinite(value) ? value.toLocaleString('zh-CN', { maximumFractionDigits: 8 }) : '—';
const message = e => typeof e.response?.data?.detail === 'string' ? e.response.data.detail : e.message;

async function loadPage (nextPage = 1) {
  const version = ++listVersion;
  loading.value = true;
  error.value = '';
  page.value = nextPage;
  try {
    const { data } = await axios.get('/api/history', { params: historyQuery(appliedFilters, nextPage) });
    if (version !== listVersion) return;
    total.value = data.total;
    rows.value = data.symbols || data.histories || [];
    if (!rows.value.length && data.total && nextPage > 1) return loadPage(Math.ceil(data.total / 20));
  } catch (e) {
    if (version === listVersion) { error.value = `读取历史失败：${message(e)}`; rows.value = []; }
  } finally {
    if (version === listVersion) loading.value = false;
  }
}
async function refresh () {
  await Promise.all([loadPage(page.value), axios.get('/api/history/overview')
    .then(({ data }) => { overview.value = data; })
    .catch(e => notify(`容量统计读取失败：${message(e)}`, { tone: 'error' }))]);
}
function closeDetail () {
  ++detailVersion; ++chartVersion;
  detail.value = null; detailLoading.value = false; chart.visible = false; chartLoading.value = false;
}
function applyFilters () {
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    notify('起始扫描日不能晚于结束扫描日', { tone: 'error' }); return;
  }
  appliedFilters = { ...filters };
  closeDetail();
  loadPage(1);
}
function switchMarket (market) { filters.market = market; filters.kind = ''; filters.code = ''; applyFilters(); }
function switchView (view) { filters.view = view; applyFilters(); }
function resetFilters () { const market = filters.market; Object.assign(filters, defaults(), { market }); applyFilters(); }
function showAppearances (code) { filters.code = code; filters.view = 'runs'; applyFilters(); }
async function openRun (runId, code = '') {
  const version = ++detailVersion;
  detailLoading.value = true; detail.value = null; chart.visible = false;
  ++chartVersion;
  await nextTick();
  detailSection.value?.scrollIntoView({ block: 'start' });
  try {
    const { data } = await axios.get(`/api/history/${encodeURIComponent(runId)}`);
    if (version !== detailVersion) return;
    detail.value = data; note.value = data.note || ''; detailCode.value = code; hitLimit.value = 50;
  } catch (e) {
    if (version === detailVersion) notify(`读取详情失败：${message(e)}`, { tone: 'error' });
  } finally { if (version === detailVersion) detailLoading.value = false; }
}
async function saveNote () {
  if (!detail.value) return;
  const runId = detail.value.run_id;
  busy.value = true;
  try {
    await axios.patch(`/api/history/${encodeURIComponent(runId)}`, { note: note.value });
    if (detail.value?.run_id === runId) detail.value.note = note.value;
    notify('备注已保存'); await loadPage(page.value);
  } catch (e) { notify(`保存失败：${message(e)}`, { tone: 'error' }); }
  finally { busy.value = false; }
}
async function togglePinned () {
  const runId = detail.value.run_id, pinned = !detail.value.pinned;
  busy.value = true;
  try {
    await axios.patch(`/api/history/${encodeURIComponent(runId)}`, { pinned });
    if (detail.value?.run_id === runId) detail.value.pinned = pinned;
    await loadPage(page.value);
  } catch (e) { notify(`置顶修改失败：${message(e)}`, { tone: 'error' }); }
  finally { busy.value = false; }
}
async function removeRun (item) {
  if (!await confirm({ title: '删除这次扫描？', message: `${item.kind_label} · ${timestampLabel(item.saved_at)}。记录、入选清单和 K 线将一起删除，无法恢复。${item.pinned ? '这是一条置顶记录。' : ''}`, confirmText: '删除', danger: true })) return;
  busy.value = true;
  try {
    await axios.delete(`/api/history/${encodeURIComponent(item.run_id)}`);
    if (detail.value?.run_id === item.run_id) closeDetail();
    notify('扫描记录已删除'); await refresh();
  } catch (e) { notify(`删除失败：${message(e)}`, { tone: 'error' }); }
  finally { busy.value = false; }
}
async function cleanup () {
  busy.value = true;
  try {
    const payload = cleanupPayload(cleanupForm);
    const { data: preview } = await axios.post('/api/history/cleanup', payload);
    if (!preview.deleted) { notify('没有需要清理的记录'); return; }
    const scope = cleanupForm.kind ? HISTORY_KINDS[cleanupForm.kind].label : '全部市场、全部类型';
    if (!await confirm({ title: `清理 ${preview.deleted} 次扫描？`, message: `范围：${scope}。预计保留 ${preview.kept} 次扫描，置顶记录跳过。删除包含 K 线且不可恢复；最终数量以执行时为准。`, confirmText: '确认清理', danger: true })) return;
    const { data } = await axios.post('/api/history/cleanup', { ...payload, apply: true });
    closeDetail(); notify(`已清理 ${data.deleted} 次扫描，保留 ${data.kept} 次`); await refresh();
  } catch (e) { notify(`清理失败：${message(e)}`, { tone: 'error' }); }
  finally { busy.value = false; }
}
async function showChart (hit, ruleId) {
  const runId = detail.value.run_id, { code, name } = hitIdentity(hit), version = ++chartVersion;
  chartLoading.value = true;
  try {
    const { data } = await axios.get(`/api/history/${encodeURIComponent(runId)}/kline/${encodeURIComponent(code)}`);
    if (version !== chartVersion || detail.value?.run_id !== runId) return;
    if (!data.kline_data.length) { notify('这条记录没有 K 线快照'); return; }
    Object.assign(chart, { visible: true, title: `${name} · ${code} · 扫描时快照`, rows: data.kline_data, marks: hitMarks(hit, ruleId) });
  } catch (e) { if (version === chartVersion) notify(`K 线读取失败：${message(e)}`, { tone: 'error' }); }
  finally { if (version === chartVersion) chartLoading.value = false; }
}
onActivated(() => {
  const hash = window.location.hash;
  if (hash !== lastHash) {
    const query = new URLSearchParams(hash.split('?')[1] || '');
    const kind = query.get('kind');
    Object.assign(filters, defaults(), { market: HISTORY_KINDS[kind]?.market || (query.get('market') === 'crypto' ? 'crypto' : 'a'), kind: HISTORY_KINDS[kind] ? kind : '' });
    appliedFilters = { ...filters }; page.value = 1; closeDetail(); lastHash = hash;
  }
  refresh();
});
onDeactivated(() => { ++listVersion; loading.value = false; closeDetail(); });
</script>

<style scoped>
.history-field { display: flex; flex-direction: column; gap: .4rem; font-size: .8125rem; }
.history-table th { background: var(--muted); font-weight: 500; white-space: nowrap; }
.history-table th, .history-table td { padding: .875rem 1rem; border-bottom: 1px solid var(--border); }
.history-table tbody tr:last-child td { border-bottom: 0; }
.history-table td { vertical-align: top; }
.history-table td .flex { white-space: nowrap; }
.history-page button:focus-visible, .history-page summary:focus-visible, .history-page a:focus-visible { outline: 2px solid var(--ring); outline-offset: 3px; }
</style>
