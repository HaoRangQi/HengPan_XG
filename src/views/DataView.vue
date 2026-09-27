<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <div class="mb-6">
      <h1 class="text-xl font-semibold">数据管理</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        管理本地 60 分钟行情库，同时查看 Baostock 数据源与字段含义。
      </p>
    </div>

    <!-- 本地行情库 -->
    <section class="rounded-lg border border-border bg-card px-5 py-4 sm:px-6" aria-label="本地行情库">
      <div>
        <h2 class="text-base font-semibold">本地行情库</h2>
        <p v-if="store" class="mt-0.5 text-xs text-muted-foreground">
          {{ store.database.path }} · {{ formatBytes(store.database.size) }} · 股票池 {{ store.stock_count }} 只 · 交易日 {{ store.trade_days }} 天
        </p>
        <p v-else class="mt-0.5 text-xs text-muted-foreground">加载中…</p>
      </div>

      <!-- 同步设置：起止日期 + 快捷范围 + 板块 -->
      <div class="mt-4 rounded-md border border-border p-4">
        <div class="flex flex-wrap items-end gap-3">
          <label class="field"><span>起始日期</span><input v-model="syncForm.start" class="input w-40" type="date" :disabled="syncing"></label>
          <label class="field"><span>结束日期</span><input v-model="syncForm.end" class="input w-40" type="date" :disabled="syncing"></label>
          <div class="flex flex-wrap gap-1.5">
            <button v-for="range in SYNC_QUICK_RANGES" :key="range.label" type="button" class="btn h-10 px-3 text-xs" :disabled="syncing" @click="applyQuickRange(range)">{{ range.label }}</button>
          </div>
          <button type="button" class="btn btn-primary ml-auto h-10 px-4" :disabled="syncing || storeLoading || !selectedBoards.length" @click="startStoreSync">
            <i :class="['fas mr-1.5', syncing ? 'fa-spinner fa-spin' : 'fa-rotate']" aria-hidden="true"></i>
            {{ syncing ? '同步中…' : '同步 60 分钟线' }}
          </button>
        </div>
        <fieldset class="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs" :disabled="syncing">
          <label v-for="board in boardOptions" :key="board.key" class="flex items-center gap-1.5">
            <input v-model="boardSelection[board.key]" type="checkbox" class="h-3.5 w-3.5 accent-primary">
            <span>{{ board.label }}</span>
          </label>
        </fieldset>
        <p class="mt-2 text-xs text-muted-foreground">
          <i class="fas fa-circle-info mr-1" aria-hidden="true"></i>起始日期留空 = 按本地进度增量同步（只补最新缺口）；填了则同步指定区间。科创板默认不勾。
        </p>
      </div>
      <div v-if="storeError" class="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{{ storeError }}</div>
      <div v-if="syncMessage" class="mt-3 rounded-md bg-foreground/[0.04] px-3 py-2 text-xs text-muted-foreground">
        <div class="flex items-center gap-3">
          <span class="min-w-0 flex-1">{{ syncMessage }}<span v-if="syncTask"> · {{ syncTask.progress }}%</span></span>
          <button v-if="syncing" type="button" class="shrink-0 text-destructive underline" @click="cancelStoreSync">停止</button>
        </div>
        <div v-if="syncTask" class="mt-2 h-1.5 overflow-hidden rounded bg-foreground/10">
          <div class="h-full bg-primary transition-[width]" :style="{ width: `${syncTask.progress || 0}%` }"></div>
        </div>
      </div>
      <div v-if="store" class="mt-4 overflow-x-auto rounded-md border border-border">
        <table class="min-w-full whitespace-nowrap text-sm">
          <thead class="bg-foreground/[0.03]"><tr class="text-left">
            <th class="px-3 py-2 font-medium">板块</th><th class="px-3 py-2 font-medium">K 线</th>
            <th class="px-3 py-2 font-medium">已有 / 股票池</th><th class="px-3 py-2 font-medium">范围</th>
            <th class="px-3 py-2 text-right font-medium">操作</th>
          </tr></thead>
          <tbody class="divide-y divide-border"><tr v-for="board in store.boards" :key="board.board">
            <td class="px-3 py-2">{{ board.label }}</td><td class="px-3 py-2">{{ board.rows.toLocaleString() }} 根</td>
            <td class="px-3 py-2">{{ board.codes.toLocaleString() }} / {{ (board.pool_codes || 0).toLocaleString() }} 只</td>
            <td class="px-3 py-2 text-xs text-muted-foreground">{{ board.first_date || '—' }} ~ {{ board.last_date || '—' }}</td>
            <td class="px-3 py-2 text-right">
              <button type="button" class="text-xs text-destructive disabled:opacity-40" :disabled="!board.rows || maintenanceRunning || syncing" @click="clearBoard(board)">
                <i class="fas fa-trash-can mr-1" aria-hidden="true"></i>清空
              </button>
            </td>
          </tr></tbody>
        </table>
      </div>
      <!-- 维护：保留天数清理 + 数据库压缩 -->
      <div class="mt-4 flex flex-wrap items-end gap-3 border-t border-border pt-4">
        <label class="field"><span>行情保留天数</span><input v-model.number="keepDays" class="input w-28" type="number" min="1" max="3650"></label>
        <button type="button" class="btn h-10 px-4" :disabled="cleanupRunning || syncing || !selectedBoards.length" @click="previewCleanup">预览清理</button>
        <button type="button" class="btn h-10 px-4" :disabled="maintenanceRunning || syncing" @click="vacuumStore">
          <i class="fas fa-compress mr-1.5" aria-hidden="true"></i>压缩数据库
        </button>
      </div>
      <p v-if="localError" class="mt-3 text-sm text-destructive">{{ localError }}</p>
      <div v-if="cleanupPreview" class="mt-3 flex flex-wrap items-center gap-3 rounded-md bg-foreground/[0.04] px-3 py-2 text-xs">
        <span>{{ cleanupPreview.cutoff }} 之前共 {{ cleanupPreview.total.toLocaleString() }} 根可清理</span>
        <button v-if="cleanupPreview.total" type="button" class="text-destructive underline" :disabled="cleanupRunning" @click="applyCleanup">执行清理</button>
      </div>

      <!-- 股票清单（左）+ 数据明细（右） -->
      <div class="mt-4 grid gap-4 border-t border-border pt-4 lg:grid-cols-[22rem_1fr]">
        <!-- 股票清单 -->
        <div class="min-w-0">
          <h3 class="text-sm font-semibold">股票清单</h3>
          <div class="mt-2 flex flex-wrap gap-2">
            <select v-model="listBoard" class="input h-9 flex-1" @change="loadStockList">
              <option v-for="board in boardOptions" :key="board.key" :value="board.key">{{ board.label }}</option>
            </select>
            <select v-model="stockFilter" class="input h-9 w-28">
              <option value="all">全部</option>
              <option value="with">已有行情</option>
              <option value="without">缺行情</option>
            </select>
          </div>
          <input v-model.trim="stockKeyword" class="input mt-2 h-9" type="search" placeholder="搜索代码或名称">
          <p class="mt-2 text-xs text-muted-foreground">
            共 {{ stockList.length }} 只，其中 {{ withDataCount }} 只有行情<span v-if="filteredStocks.length !== stockList.length"> · 筛出 {{ filteredStocks.length }} 只</span>
          </p>
          <p v-if="stockListError" class="mt-2 text-sm text-destructive">{{ stockListError }}</p>
          <div class="mt-2 max-h-[28rem] overflow-auto rounded-md border border-border">
            <table class="min-w-full whitespace-nowrap text-xs">
              <thead class="sticky top-0 bg-card"><tr class="text-left">
                <th class="px-2 py-2 font-medium">代码</th><th class="px-2 py-2 font-medium">名称</th>
                <th class="px-2 py-2 font-medium">行业</th><th class="px-2 py-2 text-right font-medium">根数</th>
                <th class="px-2 py-2 font-medium">范围</th>
              </tr></thead>
              <tbody class="divide-y divide-border">
                <tr v-if="stockListLoading"><td colspan="5" class="px-2 py-6 text-center text-muted-foreground">加载中…</td></tr>
                <tr v-else-if="!filteredStocks.length"><td colspan="5" class="px-2 py-6 text-center text-muted-foreground">没有匹配的股票</td></tr>
                <template v-else>
                  <tr v-for="stock in filteredStocks" :key="stock.code"
                    :class="['cursor-pointer hover:bg-foreground/[0.03]', selectedStock?.code === stock.code && 'bg-primary/10']"
                    @click="selectStock(stock)">
                    <td class="px-2 py-1.5 font-mono tabular-nums">{{ stock.code }}</td>
                    <td class="px-2 py-1.5">{{ stock.name }}</td>
                    <td class="px-2 py-1.5 text-muted-foreground">{{ stock.industry || '—' }}</td>
                    <td class="px-2 py-1.5 text-right tabular-nums" :class="stock.bars ? '' : 'text-muted-foreground'">{{ (stock.bars || 0).toLocaleString() }}</td>
                    <td class="px-2 py-1.5 text-muted-foreground">{{ stock.first_date ? `${stock.first_date} ~ ${stock.last_date}` : '缺行情' }}</td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 数据明细 -->
        <div class="min-w-0">
          <h3 class="text-sm font-semibold">数据明细</h3>
          <template v-if="selectedStock">
            <p class="mt-2 text-sm">
              <span class="font-mono">{{ selectedStock.code }}</span>
              <span class="ml-2 font-medium">{{ selectedStock.name }}</span>
              <span class="ml-2 text-xs text-muted-foreground">{{ selectedStock.industry || '未知行业' }} · {{ boardLabel(selectedStock.board) }}</span>
            </p>
            <form class="mt-2 flex flex-wrap items-end gap-3" @submit.prevent="queryDetail">
              <label class="field"><span>起始日期</span><input v-model="detailForm.start" class="input w-40" type="date"></label>
              <label class="field"><span>结束日期</span><input v-model="detailForm.end" class="input w-40" type="date"></label>
              <label class="field"><span>复权</span><select v-model="detailForm.adjust" class="input h-10 w-28">
                <option value="qfq">前复权</option><option value="hfq">后复权</option><option value="raw">不复权</option>
              </select></label>
              <button type="submit" class="btn h-10 px-4" :disabled="detailLoading">{{ detailLoading ? '查询中…' : '查询' }}</button>
              <button type="button" class="btn h-10 px-4" :disabled="!detailTotal || exporting" @click="exportDetailCsv">
                <i class="fas fa-file-csv mr-1.5" aria-hidden="true"></i>{{ exporting ? '导出中…' : '导出 CSV' }}
              </button>
              <button type="button" class="btn h-10 px-4" :disabled="maintenanceRunning || syncing" @click="refetchDetail">
                <i class="fas fa-arrows-rotate mr-1.5" aria-hidden="true"></i>重新拉取
              </button>
              <button type="button" class="btn h-10 px-4 text-destructive" :disabled="maintenanceRunning || syncing" @click="deleteDetail">
                <i class="fas fa-trash-can mr-1.5" aria-hidden="true"></i>删除区间
              </button>
            </form>
            <p v-if="detailError" class="mt-3 text-sm text-destructive">{{ detailError }}</p>
            <div class="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
              <span class="text-muted-foreground">
                <template v-if="detailTotal">第 {{ detailRangeStart }}-{{ detailRangeEnd }} 条，共 {{ detailTotal.toLocaleString() }} 条</template>
                <template v-else>共 0 条</template>
              </span>
              <div v-if="detailTotalPages > 1" class="flex items-center gap-2">
                <button type="button" class="btn h-8 px-3" :disabled="detailPage <= 1 || detailLoading" @click="goDetailPage(detailPage - 1)">上一页</button>
                <span class="tabular-nums">第 {{ detailPage }} / {{ detailTotalPages }} 页</span>
                <button type="button" class="btn h-8 px-3" :disabled="detailPage >= detailTotalPages || detailLoading" @click="goDetailPage(detailPage + 1)">下一页</button>
              </div>
            </div>
            <div class="mt-2 max-h-[28rem] overflow-auto rounded-md border border-border">
              <table class="min-w-full whitespace-nowrap text-xs">
                <thead class="sticky top-0 bg-card"><tr class="text-left">
                  <th v-for="col in DETAIL_COLUMNS" :key="col.key" class="px-3 py-2 font-medium">{{ col.label }}</th>
                </tr></thead>
                <tbody class="divide-y divide-border">
                  <tr v-if="detailLoading"><td :colspan="DETAIL_COLUMNS.length" class="px-3 py-6 text-center text-muted-foreground">加载中…</td></tr>
                  <tr v-else-if="!detailRows.length"><td :colspan="DETAIL_COLUMNS.length" class="px-3 py-6 text-center text-muted-foreground">没有数据</td></tr>
                  <template v-else>
                    <tr v-for="(row, index) in detailRows" :key="index">
                      <td v-for="col in DETAIL_COLUMNS" :key="col.key" class="px-3 py-1.5 font-mono tabular-nums">{{ formatCell(row[col.key], col.kind) }}</td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </template>
          <p v-else class="mt-2 rounded-md bg-foreground/[0.04] px-3 py-10 text-center text-sm text-muted-foreground">
            从左侧股票清单选择一只股票，查看它的本地行情明细
          </p>
        </div>
      </div>
      <div v-if="store?.logs?.length" class="mt-4 overflow-x-auto rounded-md border border-border">
        <table class="min-w-full whitespace-nowrap text-xs">
          <thead class="bg-foreground/[0.03]"><tr class="text-left">
            <th class="px-3 py-2 font-medium">时间</th><th class="px-3 py-2 font-medium">操作</th>
            <th class="px-3 py-2 font-medium">状态</th><th class="px-3 py-2 font-medium">请求</th>
            <th class="px-3 py-2 font-medium">行数</th><th class="px-3 py-2 font-medium">说明</th>
          </tr></thead>
          <tbody class="divide-y divide-border"><tr v-for="log in store.logs" :key="log.id">
            <td class="px-3 py-2">{{ formatDateTime(log.started_at) }}</td><td class="px-3 py-2">{{ actionLabel(log.action) }}</td>
            <td class="px-3 py-2" :class="log.status === 'failed' ? 'text-destructive' : ''">{{ statusLabel(log.status) }}</td>
            <td class="px-3 py-2 tabular-nums">{{ log.requests || 0 }}</td><td class="px-3 py-2 tabular-nums">{{ (log.rows || 0).toLocaleString() }}</td>
            <td class="max-w-xs truncate px-3 py-2 text-muted-foreground" :title="log.message || ''">{{ log.message || '—' }}</td>
          </tr></tbody>
        </table>
      </div>
    </section>

    <!-- 数据源状态 -->
    <section class="mt-6 rounded-lg border border-border bg-card px-5 py-4 sm:px-6" aria-label="数据源状态">
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
      <p v-if="sourceError" class="px-5 py-6 text-sm text-destructive sm:px-6">无法加载数据集目录，请确认后端已在 18001 端口启动。</p>
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
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue';
import axios from 'axios';

const source = ref(null);
const sourceError = ref('');
const datasets = ref([]);
const open = reactive({});
const details = reactive({}); // key -> 'loading' | 错误文本 | 字段详情
const store = ref(null);
const storeError = ref('');
const storeLoading = ref(false);
const syncing = ref(false);
const syncTask = ref(null);
const syncMessage = ref('');
let syncTimer = null;
const cleanupRunning = ref(false);
const maintenanceRunning = ref(false);
const localError = ref('');
const cleanupPreview = ref(null);
const keepDays = ref(60);
const boardOptions = [
  { key: 'sh_main', label: '沪市主板' },
  { key: 'sz_main', label: '深市主板' },
  { key: 'sz_gem', label: '创业板' },
  { key: 'sh_star', label: '科创板' },
];
const boardSelection = reactive({ sh_main: true, sz_main: true, sz_gem: true, sh_star: false });
const selectedBoards = computed(() => boardOptions.filter(board => boardSelection[board.key]).map(board => board.key));
const boardLabel = (key) => boardOptions.find(board => board.key === key)?.label || key;

// 把 Date 格式化成 <input type="date"> 需要的 YYYY-MM-DD（按本地时区，避免 UTC 偏移）
function toDateInput (date) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// ---- 同步：起始日期留空表示增量同步，快捷按钮填充起止日期 ----
const syncForm = reactive({ start: '', end: '' });
const SYNC_QUICK_RANGES = [
  { label: '最近30天', days: 30 },
  { label: '最近60天', days: 60 },
  { label: '近半年', days: 182 },
  { label: '今年', year: true },
];

// ---- 股票清单：一次拉一个板块的全部股票，搜索与筛选都在本地做 ----
const listBoard = ref('sh_main');
const stockList = ref([]);
const stockListLoading = ref(false);
const stockListError = ref('');
const stockKeyword = ref('');
const stockFilter = ref('all'); // all | with | without
const selectedStock = ref(null);
const withDataCount = computed(() => stockList.value.filter(stock => (stock.bars || 0) > 0).length);
const filteredStocks = computed(() => {
  const keyword = stockKeyword.value.toLowerCase();
  return stockList.value.filter(stock => {
    const hasData = (stock.bars || 0) > 0;
    if (stockFilter.value === 'with' && !hasData) return false;
    if (stockFilter.value === 'without' && hasData) return false;
    if (keyword && !stock.code.toLowerCase().includes(keyword) && !(stock.name || '').toLowerCase().includes(keyword)) return false;
    return true;
  });
});

// ---- 数据明细：每页 100 行，用后端返回的 total 分页 ----
const DETAIL_PAGE_SIZE = 100;
const DETAIL_COLUMNS = [
  { key: 'date', label: '时间' },
  { key: 'open', label: '开', kind: 'price' },
  { key: 'high', label: '高', kind: 'price' },
  { key: 'low', label: '低', kind: 'price' },
  { key: 'close', label: '收', kind: 'price' },
  { key: 'volume', label: '成交量', kind: 'count' },
  { key: 'amount', label: '成交额', kind: 'count' },
];

// 复权价是原始价乘以因子算出来的，会带浮点尾巴（395.8067699827114）。
// Baostock 的价格本身就是 4 位小数，按 4 位收敛既去掉噪声又不丢精度。
function formatCell (value, kind) {
  if (value === null || value === undefined || value === '') return '—';
  if (kind === 'price') return Number(value).toFixed(4);
  if (kind === 'count') return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  return value;
}
const detailForm = reactive({ start: '', end: '', adjust: 'qfq' });
const detailRows = ref([]);
const detailTotal = ref(0);
const detailLoading = ref(false);
const detailError = ref('');
const detailPage = ref(1);
const exporting = ref(false);
const detailTotalPages = computed(() => Math.max(1, Math.ceil(detailTotal.value / DETAIL_PAGE_SIZE)));
const detailRangeStart = computed(() => (detailTotal.value ? (detailPage.value - 1) * DETAIL_PAGE_SIZE + 1 : 0));
const detailRangeEnd = computed(() => Math.min(detailPage.value * DETAIL_PAGE_SIZE, detailTotal.value));

function formatBytes (bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

async function loadStore () {
  storeLoading.value = true;
  try {
    const { data } = await axios.get('/api/store/overview');
    store.value = data;
    keepDays.value = data.retention_days || keepDays.value;
    storeError.value = '';
    if (data.active_sync && !syncing.value) {
      syncing.value = true;
      syncTask.value = data.active_sync;
      syncMessage.value = data.active_sync.message;
      pollStoreSync(data.active_sync.task_id);
    }
  } catch (e) {
    storeError.value = e.response?.data?.detail || e.message;
  } finally {
    storeLoading.value = false;
  }
}

async function pollStoreSync (taskId) {
  try {
    const { data } = await axios.get(`/api/store/sync/status/${taskId}`);
    syncTask.value = data;
    syncMessage.value = data.status === 'failed' && data.error ? data.error.split('\n')[0] : data.message;
    if (['completed', 'failed', 'cancelled'].includes(data.status)) {
      syncing.value = false;
      await loadStore();
      await loadStockList();
      return;
    }
    if (syncTimer) clearTimeout(syncTimer);
    syncTimer = setTimeout(() => pollStoreSync(taskId), 1500);
  } catch (e) {
    syncing.value = false;
    syncMessage.value = e.response?.data?.detail || e.message;
  }
}

async function startStoreSync () {
  syncing.value = true;
  syncMessage.value = '正在创建同步任务…';
  try {
    const { data } = await axios.post('/api/store/sync', {
      boards: selectedBoards.value,
      frequency: '60',
      start: syncForm.start || null,
      end: syncForm.end || null,
      force_metadata: false,
      workers: 3,
    });
    syncTask.value = { task_id: data.task_id, progress: 0 };
    await pollStoreSync(data.task_id);
  } catch (e) {
    syncing.value = false;
    syncMessage.value = e.response?.data?.detail || e.message;
  }
}

async function cancelStoreSync () {
  if (!syncTask.value?.task_id) return;
  try {
    await axios.post(`/api/store/sync/cancel/${syncTask.value.task_id}`);
    syncMessage.value = '已请求停止，等待当前请求收口…';
  } catch (e) {
    syncMessage.value = e.response?.data?.detail || e.message;
  }
}

// 同步日期快捷范围：填充起止日期框
function applyQuickRange (range) {
  const now = new Date();
  syncForm.end = toDateInput(now);
  syncForm.start = range.year
    ? `${now.getFullYear()}-01-01`
    : toDateInput(new Date(now.getTime() - range.days * 86400000));
}

// ---- 股票清单 ----
async function loadStockList () {
  stockListLoading.value = true;
  stockListError.value = '';
  try {
    const { data } = await axios.get('/api/store/stocks', { params: { boards: listBoard.value, having: 'all' } });
    stockList.value = data.stocks || [];
    // 刷新后同步选中项的引用，让根数、日期范围跟着更新
    if (selectedStock.value) {
      const fresh = stockList.value.find(stock => stock.code === selectedStock.value.code);
      if (fresh) selectedStock.value = fresh;
    }
  } catch (e) {
    stockList.value = [];
    stockListError.value = e.response?.data?.detail || e.message;
  } finally {
    stockListLoading.value = false;
  }
}

function selectStock (stock) {
  selectedStock.value = stock;
  detailForm.start = (stock.first_date || '').slice(0, 10);
  detailForm.end = (stock.last_date || '').slice(0, 10);
  detailPage.value = 1;
  detailError.value = '';
  if (stock.first_date) {
    loadDetail();
  } else {
    detailRows.value = [];
    detailTotal.value = 0;
  }
}

// ---- 数据明细 ----
function detailParams (extra = {}) {
  return {
    code: selectedStock.value.code,
    start: detailForm.start || undefined,
    end: detailForm.end || undefined,
    adjust: detailForm.adjust,
    ...extra,
  };
}

async function loadDetail () {
  if (!selectedStock.value) return;
  detailLoading.value = true;
  detailError.value = '';
  try {
    const { data } = await axios.get('/api/store/kline', {
      params: detailParams({ limit: DETAIL_PAGE_SIZE, offset: (detailPage.value - 1) * DETAIL_PAGE_SIZE }),
    });
    detailRows.value = data.rows || [];
    detailTotal.value = data.total || 0;
  } catch (e) {
    detailRows.value = [];
    detailTotal.value = 0;
    detailError.value = e.response?.data?.detail || e.message;
  } finally {
    detailLoading.value = false;
  }
}

function queryDetail () {
  detailPage.value = 1;
  loadDetail();
}

function goDetailPage (target) {
  const page = Math.min(Math.max(1, target), detailTotalPages.value);
  if (page === detailPage.value) return;
  detailPage.value = page;
  loadDetail();
}

// CSV 单元格转义：含逗号、引号或换行时用双引号包裹
function csvCell (value) {
  if (value == null) return '';
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

async function exportDetailCsv () {
  if (!selectedStock.value) return;
  exporting.value = true;
  detailError.value = '';
  try {
    // 导出当前查询的全部结果（上限 5000），而不只是当前页
    const { data } = await axios.get('/api/store/kline', { params: detailParams({ limit: 5000, offset: 0 }) });
    const rows = data.rows || [];
    if (!rows.length) {
      detailError.value = '当前查询没有数据可导出';
      return;
    }
    const lines = [DETAIL_COLUMNS.map(col => col.label).join(',')];
    for (const row of rows) {
      lines.push(DETAIL_COLUMNS.map(col => csvCell(row[col.key])).join(','));
    }
    // 前缀 BOM，避免 Excel 打开中文乱码
    const blob = new Blob([`﻿${lines.join('\n')}`], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${selectedStock.value.code}_${detailForm.start || 'all'}_${detailForm.end || 'all'}_${detailForm.adjust}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    detailError.value = e.response?.data?.detail || e.message;
  } finally {
    exporting.value = false;
  }
}

async function refetchDetail () {
  if (!selectedStock.value) return;
  if (!detailForm.start || !detailForm.end) {
    detailError.value = '重新拉取需要起始日期和结束日期';
    return;
  }
  maintenanceRunning.value = true;
  detailError.value = '';
  try {
    const { data } = await axios.post('/api/store/refetch', {
      code: selectedStock.value.code,
      start: detailForm.start,
      end: detailForm.end,
    });
    syncMessage.value = `${data.code} 已重新拉取 ${data.rows.toLocaleString()} 根 K 线`;
    detailPage.value = 1;
    await loadDetail();
    await loadStore();
    await loadStockList();
  } catch (e) {
    detailError.value = e.response?.data?.detail || e.message;
  } finally {
    maintenanceRunning.value = false;
  }
}

async function deleteDetail () {
  if (!selectedStock.value) return;
  if (!window.confirm(`删除 ${selectedStock.value.code} 在 ${detailForm.start || '最早'} ~ ${detailForm.end || '最新'} 内的本地 K 线？`)) return;
  maintenanceRunning.value = true;
  detailError.value = '';
  try {
    const { data } = await axios.delete('/api/store/kline', {
      params: {
        code: selectedStock.value.code,
        start: detailForm.start || undefined,
        end: detailForm.end || undefined,
      },
    });
    syncMessage.value = `${data.code} 已删除 ${data.deleted.toLocaleString()} 根 K 线`;
    detailRows.value = [];
    detailTotal.value = 0;
    await loadStore();
    await loadStockList();
  } catch (e) {
    detailError.value = e.response?.data?.detail || e.message;
  } finally {
    maintenanceRunning.value = false;
  }
}

async function clearBoard (board) {
  if (!window.confirm(`清空${board.label}的 ${board.rows.toLocaleString()} 根本地 K 线？`)) return;
  maintenanceRunning.value = true;
  localError.value = '';
  try {
    const { data } = await axios.delete(`/api/store/board/${board.board}`);
    syncMessage.value = `${board.label}已清空 ${data.deleted.toLocaleString()} 根 K 线`;
    await loadStore();
  } catch (e) {
    localError.value = e.response?.data?.detail || e.message;
  } finally {
    maintenanceRunning.value = false;
  }
}

async function previewCleanup () {
  cleanupRunning.value = true;
  localError.value = '';
  try {
    const { data } = await axios.post('/api/store/cleanup', { boards: selectedBoards.value, keep_days: keepDays.value, apply: false });
    cleanupPreview.value = data;
  } catch (e) {
    localError.value = e.response?.data?.detail || e.message;
  } finally {
    cleanupRunning.value = false;
  }
}

async function applyCleanup () {
  if (!window.confirm(`删除 ${cleanupPreview.value.total.toLocaleString()} 根过期 K 线？`)) return;
  cleanupRunning.value = true;
  try {
    await axios.post('/api/store/cleanup', { boards: selectedBoards.value, keep_days: keepDays.value, apply: true });
    cleanupPreview.value = null;
    await loadStore();
  } catch (e) {
    localError.value = e.response?.data?.detail || e.message;
  } finally {
    cleanupRunning.value = false;
  }
}

async function vacuumStore () {
  maintenanceRunning.value = true;
  localError.value = '';
  try {
    const { data } = await axios.post('/api/store/vacuum');
    syncMessage.value = `数据库压缩完成，释放 ${formatBytes(data.freed)}`;
    await loadStore();
  } catch (e) {
    localError.value = e.response?.data?.detail || e.message;
  } finally {
    maintenanceRunning.value = false;
  }
}

function formatDateTime (value) {
  return value ? value.replace('T', ' ') : '—';
}

function actionLabel (action) {
  return ({ sync: '同步', cleanup: '清理', refetch: '重拉', delete: '删除', clear: '清空', vacuum: '压缩' })[action] || action;
}

function statusLabel (status) {
  return ({ running: '进行中', completed: '完成', cancelled: '已停止', failed: '失败' })[status] || status;
}

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
  await loadStore();
  loadStockList();
  try {
    const { data } = await axios.get('/api/data/sources');
    source.value = data.source;
    datasets.value = data.datasets;
    form.dataset = data.datasets[0]?.key || '';
  } catch (e) {
    sourceError.value = e.message;
  }
});

onUnmounted(() => {
  if (syncTimer) clearTimeout(syncTimer);
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
