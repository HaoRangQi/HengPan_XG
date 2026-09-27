<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <div class="mb-6">
      <h1 class="text-xl font-semibold">数据管理</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        查看可用的数据源与字段含义，并按证券代码预览原始数据。本页只读，不写入任何数据。
      </p>
    </div>

    <!-- 数据源状态 -->
    <section class="rounded-lg border border-border bg-card px-5 py-4 sm:px-6" aria-label="数据源状态">
      <div class="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
        <span class="flex items-center gap-2">
          <span :class="['h-2 w-2 rounded-full', statusDot]" aria-hidden="true"></span>
          <template v-if="!source && !sourceError">正在检测数据源…</template>
          <template v-else-if="sourceError">接口不可用：{{ sourceError }}</template>
          <template v-else>
            <span class="font-medium">{{ source.name }}</span>
            <span class="text-muted-foreground">
              {{ source.server.reachable ? `已连通 · ${source.server.latency_ms} ms` : `不可达 · ${source.server.error || ''}` }}
            </span>
          </template>
        </span>
        <template v-if="source">
          <span class="text-muted-foreground">客户端 <span class="text-foreground">{{ source.client_version }}</span></span>
          <span class="text-muted-foreground">服务器 <span class="font-mono text-foreground">{{ source.server.host }}:{{ source.server.port }}</span></span>
          <span class="text-muted-foreground">存储 <span class="text-foreground">{{ source.storage }}</span></span>
        </template>
      </div>
    </section>

    <!-- 数据集 -->
    <section class="mt-6 rounded-lg border border-border bg-card" aria-label="可用数据集">
      <div class="border-b border-border px-5 py-4 sm:px-6">
        <h2 class="text-base font-semibold">可用数据集</h2>
        <p class="mt-0.5 text-xs text-muted-foreground">点击展开查看字段含义和用途</p>
      </div>
      <p v-if="sourceError" class="px-5 py-6 text-sm text-destructive sm:px-6">无法加载数据集目录，请确认后端已在 8001 端口启动。</p>
      <p v-else-if="!datasets.length" class="px-5 py-6 text-sm text-muted-foreground sm:px-6">加载中…</p>
      <ul v-else class="divide-y divide-border">
        <li v-for="d in datasets" :key="d.key">
          <button type="button" class="flex w-full items-start gap-3 px-5 py-3 text-left hover:bg-foreground/[0.03] sm:px-6"
            :aria-expanded="!!open[d.key]" @click="toggleDataset(d.key)">
            <i :class="['fas fa-chevron-right mt-1 text-xs text-muted-foreground transition-transform duration-150', open[d.key] && 'rotate-90']"
              aria-hidden="true"></i>
            <span class="min-w-0 flex-1">
              <span class="flex flex-wrap items-baseline gap-x-3">
                <span class="text-sm font-medium">{{ d.name }}</span>
                <span class="text-sm text-muted-foreground">{{ d.summary }}</span>
              </span>
              <span class="mt-0.5 block text-xs text-muted-foreground">
                <code class="code">{{ d.api }}</code> · {{ d.scale }} · {{ d.field_count }} 个字段 · 参数 {{ d.params.join('、') }}
              </span>
            </span>
          </button>
          <div v-if="open[d.key]" class="px-5 pb-4 pl-11 sm:px-6 sm:pl-12">
            <p v-if="details[d.key] === 'loading'" class="text-sm text-muted-foreground">加载中…</p>
            <p v-else-if="typeof details[d.key] === 'string'" class="text-sm text-destructive">{{ details[d.key] }}</p>
            <template v-else-if="details[d.key]">
              <p class="mb-3 rounded-md bg-foreground/[0.04] px-3 py-2 text-xs text-muted-foreground">
                <span class="font-medium text-foreground">用途</span> · {{ details[d.key].used_by }}
              </p>
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-border text-left text-xs text-muted-foreground">
                    <th class="py-2 pr-4 font-medium">字段</th>
                    <th class="py-2 font-medium">含义</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-border">
                  <tr v-for="f in details[d.key].fields" :key="f[0]">
                    <td class="py-1.5 pr-4 align-top"><code class="code">{{ f[0] }}</code></td>
                    <td class="py-1.5">{{ f[1] }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
          </div>
        </li>
      </ul>
    </section>

    <!-- 数据预览 -->
    <section class="mt-6 rounded-lg border border-border bg-card" aria-label="数据预览">
      <div class="border-b border-border px-5 py-4 sm:px-6">
        <h2 class="text-base font-semibold">数据预览</h2>
        <p class="mt-0.5 text-xs text-muted-foreground">{{ hint }}</p>
      </div>
      <form class="flex flex-wrap items-end gap-4 px-5 py-4 sm:px-6" @submit.prevent="runQuery">
        <label class="field">
          <span>数据集</span>
          <select v-model="form.dataset" class="input h-10 w-44">
            <option v-for="d in datasets" :key="d.key" :value="d.key">{{ d.name }}</option>
          </select>
        </label>
        <label class="field">
          <span>证券代码</span>
          <input v-model.trim="form.code" class="input w-36" placeholder="sh.600000">
        </label>
        <template v-if="form.dataset === 'kline'">
          <label class="field">
            <span>起始日期</span>
            <input v-model="form.start" class="input w-44" type="date">
          </label>
          <label class="field">
            <span>结束日期</span>
            <input v-model="form.end" class="input w-44" type="date">
          </label>
        </template>
        <label v-if="isFinancial" class="field">
          <span>年份</span>
          <input v-model.number="form.year" class="input w-28" type="number">
        </label>
        <label class="field">
          <span>条数</span>
          <input v-model.number="form.limit" class="input w-24" type="number" min="1" max="500">
        </label>
        <button type="submit" class="btn btn-primary h-10 px-6" :disabled="querying || !form.dataset">
          {{ querying ? '查询中…' : '查询' }}
        </button>
      </form>

      <div v-if="queryError" class="mx-5 mb-5 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive sm:mx-6" role="alert">
        {{ queryError }}
      </div>
      <div v-else-if="preview" class="px-5 pb-5 sm:px-6">
        <p v-if="!preview.rows.length" class="rounded-md bg-foreground/[0.04] px-3 py-2 text-sm text-muted-foreground">
          查询成功，但没有返回数据。请检查代码、日期范围或年份。
        </p>
        <template v-else>
          <p class="text-xs text-muted-foreground">
            <code class="code">{{ preview.api }}</code> · {{ preview.row_count }} 条 · {{ preview.elapsed_ms }} ms
          </p>
          <p v-if="preview.truncated" class="mt-2 text-xs text-muted-foreground">{{ preview.truncated_note }}</p>
          <div class="mt-3 overflow-x-auto rounded-md border border-border">
            <table class="min-w-full whitespace-nowrap text-sm">
              <thead class="bg-foreground/[0.03]">
                <tr class="text-left">
                  <th v-for="f in preview.fields" :key="f" class="px-3 py-2 align-bottom font-medium">
                    <code class="font-mono text-xs">{{ f }}</code>
                    <span v-if="preview.field_labels[f]" class="block text-xs font-normal text-muted-foreground">
                      {{ preview.field_labels[f] }}
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-border">
                <tr v-for="(row, i) in preview.rows" :key="i">
                  <td v-for="(cell, j) in row" :key="j" class="px-3 py-1.5 font-mono text-xs tabular-nums">
                    {{ cell === '' ? '—' : cell }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </section>
  </main>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue';
import axios from 'axios';

const source = ref(null);
const sourceError = ref('');
const datasets = ref([]);
const open = reactive({});
const details = reactive({}); // key -> 'loading' | 错误文本 | 字段详情

const statusDot = computed(() => {
  if (sourceError.value || (source.value && !source.value.server.reachable)) return 'bg-red-500';
  return source.value ? 'bg-emerald-500' : 'bg-amber-400';
});

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
  start: new Date(today.getTime() - 60 * 86400000).toISOString().slice(0, 10),
  end: today.toISOString().slice(0, 10),
  year: today.getFullYear() - 1,
  limit: 20,
});
const isFinancial = computed(() => ['growth', 'profit', 'balance'].includes(form.dataset));
const hint = computed(() => (['stock_basic', 'stock_industry'].includes(form.dataset)
  ? '代码留空可取全市场：服务端按 2000 条分页，小条数约 5 秒，取满全部约 20 秒。'
  : '此数据集必须指定证券代码。'));

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

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/data/sources');
    source.value = data.source;
    datasets.value = data.datasets;
    form.dataset = data.datasets[0]?.key || '';
  } catch (e) {
    sourceError.value = e.message;
  }
});
</script>

<style scoped>
.field {
  @apply flex flex-col gap-1.5 text-xs text-muted-foreground;
}

.code {
  @apply rounded bg-foreground/[0.06] px-1 py-px font-mono text-xs;
}
</style>
