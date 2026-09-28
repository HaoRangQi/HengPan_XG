<template>
  <div class="space-y-6">
    <!-- 数据源状态 -->
    <section class="grid gap-4 md:grid-cols-2">
      <article class="card p-5">
        <div class="flex items-center gap-3">
          <span class="source-dot" :class="baostockTone"></span>
          <div class="min-w-0 flex-1">
            <p class="text-title-m">Baostock · A 股</p>
            <p class="truncate text-body-s text-md-on-surface-variant">
              <template v-if="!source && !sourceError">正在检测…</template>
              <template v-else-if="sourceError">接口不可用：{{ sourceError }}</template>
              <template v-else>{{ source.server.reachable ? `已连通 · ${source.server.latency_ms} ms` : `不可达 · ${source.server.error || ''}` }}</template>
            </p>
          </div>
        </div>
        <dl v-if="source" class="mt-4 grid grid-cols-3 gap-3 text-body-s">
          <div><dt class="text-md-on-surface-variant">客户端</dt><dd class="mt-0.5 font-medium">{{ source.client_version }}</dd></div>
          <div class="col-span-2"><dt class="text-md-on-surface-variant">服务器</dt><dd class="mt-0.5 truncate font-mono">{{ source.server.host }}:{{ source.server.port }}</dd></div>
        </dl>
        <div class="mt-4 border-t border-md-outline-variant pt-3 text-body-s text-md-on-surface-variant">
          <p>IP 日请求 5 万次</p>
          <p class="mt-1">限制时长 = 本年累计限制次数 × 6 小时</p>
        </div>
      </article>
      <article class="card p-5">
        <div class="flex items-center gap-3">
          <span class="source-dot" :class="binanceTone"></span>
          <div class="min-w-0 flex-1">
            <p class="text-title-m">Binance 永续 · 加密</p>
            <p class="truncate text-body-s text-md-on-surface-variant">{{ binance ? binance.message : '正在检测…' }}</p>
          </div>
          <button type="button" class="icon-btn" aria-label="重新检测" @click="pingBinance"><MIcon name="refresh" /></button>
        </div>
        <dl class="mt-4 grid grid-cols-3 gap-3 text-body-s">
          <div><dt class="text-md-on-surface-variant">认证</dt><dd class="mt-0.5 font-medium">公开接口</dd></div>
          <div class="col-span-2"><dt class="text-md-on-surface-variant">限速</dt><dd class="mt-0.5">每分钟 2400 权重，不累计封禁</dd></div>
        </dl>
      </article>
    </section>

    <!-- 数据集 -->
    <section class="card overflow-hidden">
      <div class="flex items-center gap-3 p-5">
        <span class="section-icon"><MIcon name="dataset" /></span>
        <div>
          <h2 class="text-title-m">Baostock 数据集</h2>
          <p class="text-body-s text-md-on-surface-variant">点开查看字段含义和用途</p>
        </div>
      </div>
      <p v-if="sourceError" class="mx-5 mb-5 banner banner-error">无法加载数据集目录，请确认后端已在 18001 端口启动。</p>
      <ul v-else class="border-t border-md-outline-variant">
        <li v-for="d in datasets" :key="d.key" class="border-b border-md-outline-variant last:border-b-0">
          <button type="button" class="dataset-row" :aria-expanded="!!open[d.key]" data-ripple @click="toggleDataset(d.key)">
            <span class="min-w-0 flex-1 text-left">
              <span class="flex flex-wrap items-baseline gap-x-3">
                <span class="text-title-s">{{ d.name }}</span>
                <span class="text-body-m text-md-on-surface-variant">{{ d.summary }}</span>
              </span>
              <span class="mt-1 block text-body-s text-md-on-surface-variant">
                <code class="code">{{ d.api }}</code> · {{ d.scale }} · {{ d.field_count }} 个字段 · 参数 {{ d.params.join('、') }}
              </span>
            </span>
            <MIcon name="expand_more" class="expand-icon" :class="open[d.key] && 'is-open'" />
          </button>
          <Transition name="expand">
            <div v-if="open[d.key]" class="px-5 pb-5">
              <p v-if="details[d.key] === 'loading'" class="text-body-m text-md-on-surface-variant">加载中…</p>
              <p v-else-if="typeof details[d.key] === 'string'" class="banner banner-error">{{ details[d.key] }}</p>
              <template v-else-if="details[d.key]">
                <p class="banner mb-3 text-body-s"><MIcon name="lightbulb" :size="18" />{{ details[d.key].used_by }}</p>
                <div class="overflow-hidden rounded-xl border border-md-outline-variant">
                  <table class="m3-table">
                    <thead><tr><th class="w-48">字段</th><th>含义</th></tr></thead>
                    <tbody>
                      <tr v-for="f in details[d.key].fields" :key="f[0]">
                        <td><code class="code">{{ f[0] }}</code></td>
                        <td class="whitespace-normal">{{ f[1] }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
            </div>
          </Transition>
        </li>
      </ul>
    </section>

    <!-- 原始数据预览 -->
    <section class="card overflow-hidden">
      <div class="flex items-center gap-3 p-5">
        <span class="section-icon"><MIcon name="manage_search" /></span>
        <div>
          <h2 class="text-title-m">原始数据预览</h2>
          <p class="text-body-s text-md-on-surface-variant">{{ hint }}</p>
        </div>
      </div>
      <form class="flex flex-wrap items-end gap-3 border-t border-md-outline-variant p-5" @submit.prevent="runQuery">
        <label class="field">数据集
          <select v-model="form.dataset" class="input w-44">
            <option v-for="d in datasets" :key="d.key" :value="d.key">{{ d.name }}</option>
          </select>
        </label>
        <label class="field">证券代码<input v-model.trim="form.code" class="input w-36" placeholder="sh.600000"></label>
        <template v-if="form.dataset === 'kline'">
          <label class="field">起始日期<input v-model="form.start" class="input w-40" type="date"></label>
          <label class="field">结束日期<input v-model="form.end" class="input w-40" type="date"></label>
        </template>
        <label v-if="isFinancial" class="field">年份<input v-model.number="form.year" class="input w-28" type="number"></label>
        <label class="field">条数<input v-model.number="form.limit" class="input w-24" type="number" min="1" max="500"></label>
        <button type="submit" class="btn btn-filled" :disabled="querying || !form.dataset">
          <MIcon :name="querying ? 'progress_activity' : 'play_arrow'" :class="querying && 'animate-spin'" />
          {{ querying ? '查询中…' : '查询' }}
        </button>
      </form>
      <p v-if="queryError" class="mx-5 mb-5 banner banner-error" role="alert"><MIcon name="error" />{{ queryError }}</p>
      <div v-else-if="preview" class="px-5 pb-5">
        <p v-if="!preview.rows.length" class="banner">查询成功，但没有返回数据。请检查代码、日期范围或年份。</p>
        <template v-else>
          <p class="text-body-s text-md-on-surface-variant">
            <code class="code">{{ preview.api }}</code> · {{ preview.row_count }} 条 · {{ preview.elapsed_ms }} ms
          </p>
          <p v-if="preview.truncated" class="mt-1 text-body-s text-md-on-surface-variant">{{ preview.truncated_note }}</p>
          <div class="mt-3 max-h-[480px] overflow-auto rounded-xl border border-md-outline-variant">
            <table class="m3-table">
              <thead>
                <tr>
                  <th v-for="f in preview.fields" :key="f">
                    <code class="font-mono">{{ f }}</code>
                    <span v-if="preview.field_labels[f]" class="block font-normal normal-case">{{ preview.field_labels[f] }}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in preview.rows" :key="i">
                  <td v-for="(cell, j) in row" :key="j" class="font-mono">{{ cell === '' ? '—' : cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue';
import axios from 'axios';
import MIcon from '../../ui/MIcon.vue';
import { toDateInput } from './format.js';

const props = defineProps({ active: { type: Boolean, default: true } });

const source = ref(null);
const sourceError = ref('');
const datasets = ref([]);
const open = reactive({});
const details = reactive({}); // key -> 'loading' | 错误文本 | 字段详情
const binance = ref(null);

const baostockTone = computed(() => {
  if (sourceError.value || (source.value && !source.value.server.reachable)) return 'is-bad';
  return source.value ? 'is-ok' : 'is-pending';
});
const binanceTone = computed(() => (!binance.value ? 'is-pending' : binance.value.ok ? 'is-ok' : 'is-bad'));

async function pingBinance () {
  binance.value = null;
  try {
    const { data } = await axios.get('/api/crypto/ping');
    binance.value = data;
  } catch (e) {
    binance.value = { ok: false, message: e.message };
  }
}

async function toggleDataset (key) {
  open[key] = !open[key];
  if (!open[key] || (details[key] && details[key] !== 'loading' && typeof details[key] !== 'string')) return;
  details[key] = 'loading';
  try {
    const { data } = await axios.get(`/api/data/sources/${key}`);
    details[key] = data;
  } catch (e) {
    details[key] = e.message;
  }
}

// 默认值：日线取最近 60 天，财务数据取上一年年报
const today = new Date();
const form = reactive({
  dataset: '',
  code: 'sh.600000',
  start: toDateInput(new Date(today.getTime() - 60 * 86400000)),
  end: toDateInput(today),
  year: today.getFullYear() - 1,
  limit: 20,
});
const isFinancial = computed(() => ['growth', 'profit', 'balance'].includes(form.dataset));
const hint = computed(() => (['stock_basic', 'stock_industry'].includes(form.dataset)
  ? '代码留空可取全市场：服务端按 2000 条分页，小条数约 5 秒，取满全部约 20 秒。'
  : '直接调用 Baostock 接口，不经过本地库。此数据集必须指定证券代码。'));

const querying = ref(false);
const queryError = ref('');
const preview = ref(null);

async function runQuery () {
  const params = { dataset: form.dataset, limit: form.limit };
  if (form.code) params.code = form.code;
  if (form.dataset === 'kline') {
    if (form.start) params.start = form.start;
    if (form.end) params.end = form.end;
  }
  if (isFinancial.value && form.year) params.year = form.year;
  querying.value = true;
  queryError.value = '';
  preview.value = null;
  try {
    const { data } = await axios.get('/api/data/preview', { params });
    preview.value = data;
  } catch (e) {
    queryError.value = e.message;
  } finally {
    querying.value = false;
  }
}

let loaded = false;
watch(() => props.active, async (active) => {
  if (!active || loaded) return;
  loaded = true;
  pingBinance();
  try {
    const { data } = await axios.get('/api/data/sources');
    source.value = data.source;
    datasets.value = data.datasets;
    form.dataset = data.datasets[0]?.key || '';
  } catch (e) {
    sourceError.value = e.message;
  }
}, { immediate: true });
</script>

<style scoped>
.section-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}
.source-dot {
  width: 12px;
  height: 12px;
  border-radius: 9999px;
  flex-shrink: 0;
  box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 18%, transparent);
}
.source-dot.is-ok { background: var(--md-fall); color: var(--md-fall); }
.source-dot.is-bad { background: var(--md-error); color: var(--md-error); }
.source-dot.is-pending { background: var(--md-outline); color: var(--md-outline); animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.4; } }
.dataset-row {
  position: relative;
  display: flex;
  width: 100%;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  isolation: isolate;
  overflow: hidden;
  transition: background-color var(--md-duration-short);
}
.dataset-row:hover { background: color-mix(in srgb, var(--md-on-surface) 5%, transparent); }
.expand-icon { color: var(--md-on-surface-variant); transition: transform var(--md-duration-medium) var(--md-ease-emphasized); }
.expand-icon.is-open { transform: rotate(180deg); }
.expand-enter-active { transition: opacity 250ms var(--md-ease-emphasized-decelerate), transform 300ms var(--md-ease-emphasized-decelerate); }
.expand-leave-active { transition: opacity 120ms var(--md-ease-emphasized-accelerate); }
.expand-enter-from { opacity: 0; transform: translateY(-8px); }
.expand-leave-to { opacity: 0; }
</style>
