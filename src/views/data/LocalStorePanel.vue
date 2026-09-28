<template>
  <div class="space-y-6">
    <!-- 数据源连不上（目前只有加密货币会检测：Binance 对部分地区返回 451） -->
    <Transition name="slide-up">
      <div v-if="connectivity && !connectivity.ok" class="banner banner-error">
        <MIcon :name="connectivity.status === 'restricted' ? 'public_off' : 'cloud_off'" class="mt-0.5 shrink-0" />
        <div class="min-w-0 flex-1">
          <p class="text-title-s">无法访问 {{ market.sourceName }}</p>
          <p class="mt-0.5 text-body-m opacity-90">{{ connectivity.message }}</p>
        </div>
        <button type="button" class="btn btn-sm btn-text shrink-0" :disabled="pinging" style="color: inherit"
          @click="checkPing">
          <MIcon name="refresh" :class="pinging && 'animate-spin'" />重新检测
        </button>
      </div>
    </Transition>

    <!-- ================= 概览 ================= -->
    <section class="grid gap-4 sm:grid-cols-2" :class="market.groups.length > 2 ? 'xl:grid-cols-5' : 'xl:grid-cols-3'">
      <!-- 库文件卡：用主色容器做视觉锚点 -->
      <article class="hero-card rise-in" :class="market.groups.length > 2 ? 'sm:col-span-2 xl:col-span-1' : ''">
        <div class="flex items-center gap-2 text-label-l">
          <MIcon name="database" filled :size="20" />{{ market.sourceName }} · {{ market.intervalLabel }}
        </div>
        <p class="mt-4 text-display-s tabular">{{ totalRowsText }}</p>
        <p class="text-body-m opacity-80">根 K 线 · {{ formatBytes(overview?.database?.size) }}</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <span v-for="fact in facts" :key="fact.label" class="hero-chip">
            <MIcon :name="fact.icon" :size="16" />{{ fact.label }} {{ fact.value }}
          </span>
        </div>
        <p class="mt-3 truncate font-mono text-[11px] opacity-60" :title="overview?.database?.path">{{ overview?.database?.path || '…' }}</p>
      </article>

      <article v-for="(group, index) in groupStats" :key="group.key" class="stat-card lift rise-in"
        :style="{ '--i': index + 1 }">
        <div class="flex items-start justify-between">
          <span class="stat-avatar" :class="`tone-${index % 3}`"><MIcon :name="group.icon" filled :size="22" /></span>
          <button type="button" class="icon-btn -mr-2 -mt-1" :title="`清空${group.label}`"
            :disabled="!group.rows || busy" @click="clearGroup(group)">
            <MIcon name="delete_sweep" :size="20" />
          </button>
        </div>
        <p class="mt-3 text-label-l text-md-on-surface-variant">{{ group.label }}</p>
        <p class="mt-0.5 text-headline-s tabular">{{ formatCount(group.rows) }}<span class="ml-1 text-body-s text-md-on-surface-variant">根</span></p>
        <div class="progress-linear mt-3" :title="`${group.items} / ${group.pool} ${market.unit}已有数据`">
          <div class="bar" :style="{ width: `${coverage(group)}%` }"></div>
        </div>
        <p class="mt-2 flex items-center justify-between gap-2 text-body-s text-md-on-surface-variant">
          <span class="tabular">{{ formatCount(group.items) }} / {{ formatCount(group.pool) }} {{ market.unit }}</span>
          <span class="truncate tabular">{{ group.first ? `${short(group.first)} → ${short(group.last)}` : '暂无数据' }}</span>
        </p>
      </article>
    </section>
    <p v-if="overviewError" class="banner banner-error"><MIcon name="error" />{{ overviewError }}</p>

    <!-- ================= 同步 ================= -->
    <section class="card overflow-hidden">
      <div class="flex flex-wrap items-start justify-between gap-4 p-5 sm:p-6">
        <div class="flex items-center gap-3">
          <span class="section-icon"><MIcon name="cloud_sync" /></span>
          <div>
            <h2 class="text-title-l">同步行情</h2>
            <p class="text-body-s text-md-on-surface-variant">从 {{ market.sourceName }} 拉取{{ market.intervalLabel }}写入本地库</p>
          </div>
        </div>
        <button v-if="!sync.running" type="button" class="btn btn-filled btn-lg"
          :disabled="!selectedGroups.length || overviewLoading" @click="startSync">
          <MIcon name="sync" />开始同步
        </button>
        <button v-else type="button" class="btn btn-lg btn-danger-outlined" @click="cancelSync">
          <MIcon name="stop_circle" />停止
        </button>
      </div>

      <div class="grid gap-5 border-t border-md-outline-variant px-5 py-5 sm:px-6 lg:grid-cols-2">
        <div>
          <p class="text-label-m text-md-on-surface-variant">日期区间</p>
          <div class="mt-2 flex flex-wrap items-center gap-2">
            <input v-model="syncForm.start" class="input w-40" type="date" :disabled="sync.running" aria-label="起始日期">
            <MIcon name="arrow_forward" :size="18" class="text-md-on-surface-variant" />
            <input v-model="syncForm.end" class="input w-40" type="date" :disabled="sync.running" aria-label="结束日期">
            <button v-if="syncForm.start || syncForm.end" type="button" class="icon-btn" title="清空日期（改为增量同步）"
              :disabled="sync.running" @click="syncForm.start = ''; syncForm.end = ''">
              <MIcon name="backspace" :size="20" />
            </button>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button v-for="range in QUICK_RANGES" :key="range.label" type="button" class="chip"
              :class="isQuickActive(range) && 'is-selected'" :disabled="sync.running" @click="applyQuickRange(range)">
              <MIcon v-if="isQuickActive(range)" name="check" />{{ range.label }}
            </button>
          </div>
        </div>
        <div>
          <p class="text-label-m text-md-on-surface-variant">范围</p>
          <div class="mt-2 flex flex-wrap gap-2">
            <button v-for="group in market.groups" :key="group.key" type="button" class="chip"
              :class="syncForm.groups[group.key] && 'is-selected'" :disabled="sync.running"
              @click="syncForm.groups[group.key] = !syncForm.groups[group.key]">
              <MIcon :name="syncForm.groups[group.key] ? 'check' : group.icon" />{{ group.label }}
            </button>
          </div>
          <template v-if="market.volumeFilters">
            <p class="mt-4 text-label-m text-md-on-surface-variant">24 小时成交额（USDT）</p>
            <div class="segmented segmented-sm mt-2">
              <button v-for="option in market.volumeFilters" :key="option.value" type="button"
                :class="syncForm.minQuoteVolume === option.value && 'is-selected'" :disabled="sync.running"
                @click="syncForm.minQuoteVolume = option.value">
                <MIcon v-if="syncForm.minQuoteVolume === option.value" name="check" :size="16" />{{ option.label }}
              </button>
            </div>
          </template>
        </div>
      </div>

      <div class="flex items-start gap-2 px-5 pb-5 text-body-s text-md-on-surface-variant sm:px-6">
        <MIcon name="info" :size="16" class="mt-px shrink-0" />
        <span>{{ syncForm.start ? `将补 ${syncForm.start} ~ ${syncForm.end || '最新'} 的历史，所选范围内全部重拉并覆盖。` : market.syncHint }}</span>
      </div>

      <!-- 进度 -->
      <Transition name="slide-up">
        <div v-if="sync.running || sync.message" class="sync-status" :class="!sync.running && `is-${sync.tone}`">
          <div class="flex items-center gap-3">
            <MIcon :name="sync.running ? 'progress_activity' : toneIcon(sync.tone)" :class="sync.running && 'animate-spin'" :size="20" />
            <span class="min-w-0 flex-1 text-body-m">{{ sync.message }}</span>
            <span v-if="sync.running && sync.task?.progress != null" class="text-label-l tabular">{{ sync.task.progress }}%</span>
            <button v-if="!sync.running" type="button" class="icon-btn -my-2" aria-label="关闭" @click="sync.message = ''">
              <MIcon name="close" :size="18" />
            </button>
          </div>
          <div v-if="sync.running" class="progress-linear mt-3" :class="!sync.task?.total && 'is-indeterminate'">
            <div class="bar" :style="{ width: `${sync.task?.progress || 0}%` }"></div>
          </div>
        </div>
      </Transition>
    </section>

    <!-- ================= 浏览：清单 + 明细 ================= -->
    <section class="grid items-start gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
      <!-- 清单 -->
      <div class="card flex max-h-[760px] flex-col overflow-hidden">
        <div class="space-y-3 p-4">
          <div class="flex flex-wrap gap-2">
            <button v-for="group in market.groups" :key="group.key" type="button" class="chip"
              :class="list.group === group.key && 'is-selected'" @click="switchGroup(group.key)">
              <MIcon v-if="list.group === group.key" name="check" />{{ group.label }}
            </button>
          </div>
          <label class="search-field">
            <MIcon name="search" :size="20" class="text-md-on-surface-variant" />
            <input v-model.trim="list.keyword" type="search" :placeholder="`搜索${market.itemName}代码或名称`">
            <button v-if="list.keyword" type="button" class="icon-btn -mr-2 h-8 w-8" aria-label="清空搜索" @click="list.keyword = ''">
              <MIcon name="close" :size="18" />
            </button>
          </label>
          <div class="flex items-center justify-between gap-2">
            <div class="segmented segmented-sm">
              <button v-for="option in FILTERS" :key="option.key" type="button"
                :class="list.filter === option.key && 'is-selected'" @click="list.filter = option.key">
                {{ option.label }}<span class="tabular opacity-70">{{ filterCount(option.key) }}</span>
              </button>
            </div>
            <select v-model="list.sort" class="input h-8 w-auto rounded-full py-0 pl-3 text-xs" aria-label="排序">
              <option v-for="sort in market.sorts" :key="sort.key" :value="sort.key">按{{ sort.label }}</option>
            </select>
          </div>
        </div>
        <p v-if="list.error" class="mx-4 mb-3 banner banner-error text-body-s">{{ list.error }}</p>
        <div class="min-h-0 flex-1 overflow-auto border-t border-md-outline-variant">
          <div v-if="list.loading" class="space-y-2 p-4">
            <div v-for="n in 8" :key="n" class="skeleton h-12"></div>
          </div>
          <div v-else-if="!visibleItems.length" class="empty-state py-12">
            <span class="empty-icon"><MIcon name="search_off" :size="28" /></span>
            <p class="mt-3 text-body-m">{{ list.items.length ? '没有匹配的结果' : `这个分组还没有${market.itemName}，先同步一次` }}</p>
          </div>
          <ul v-else role="listbox" :aria-label="`${market.itemName}清单`">
            <li v-for="item in visibleItems" :key="market.itemTitle(item)" role="option"
              :aria-selected="selectedId === market.itemTitle(item)" class="list-item" data-ripple
              :class="selectedId === market.itemTitle(item) && 'is-selected'" @click="select(item)">
              <span class="list-avatar" :class="!item.bars && 'is-empty'">{{ market.itemAvatar(item) }}</span>
              <span class="min-w-0 flex-1">
                <span class="flex items-baseline gap-2">
                  <span class="font-mono text-body-m font-medium">{{ market.itemTitle(item) }}</span>
                  <span class="truncate text-body-s text-md-on-surface-variant">{{ market.itemLabel(item) }}</span>
                </span>
                <span class="block truncate text-body-s text-md-on-surface-variant">{{ market.itemMeta(item) }}</span>
              </span>
              <span class="shrink-0 text-right">
                <span class="block text-label-m tabular" :class="!item.bars && 'text-md-error'">
                  {{ item.bars ? `${formatCount(item.bars)} 根` : '缺数据' }}
                </span>
                <span v-for="fact in market.itemFacts(item)" :key="fact.label"
                  class="block text-body-s tabular" :class="fact.tone === 'rise' ? 'text-rise' : fact.tone === 'fall' ? 'text-fall' : 'text-md-on-surface-variant'">
                  {{ fact.value }}
                </span>
              </span>
            </li>
          </ul>
          <button v-if="filteredItems.length > visibleCount" type="button" class="btn btn-text my-2 w-full"
            @click="visibleCount += 300">
            再显示 {{ Math.min(300, filteredItems.length - visibleCount) }} 个（共 {{ filteredItems.length }}）
          </button>
        </div>
        <p class="border-t border-md-outline-variant px-4 py-2.5 text-body-s text-md-on-surface-variant">
          共 {{ formatCount(list.items.length) }} {{ market.unit }}，其中 {{ formatCount(withCount) }} {{ market.unit }}有数据
        </p>
      </div>

      <!-- 明细 -->
      <div class="card min-w-0 overflow-hidden">
        <Transition name="fade" mode="out-in">
          <div v-if="!selected" key="empty" class="empty-state min-h-[520px]">
            <span class="empty-icon empty-icon-lg"><MIcon name="table_view" :size="40" /></span>
            <p class="mt-4 text-title-m">选择一个{{ market.itemName }}</p>
            <p class="mt-1 text-body-m text-md-on-surface-variant">在左侧清单里点一下，查看它的本地{{ market.intervalLabel }}明细</p>
          </div>
          <div v-else :key="selectedId">
            <!-- 标题 -->
            <div class="flex flex-wrap items-center gap-4 p-5 sm:p-6">
              <span class="list-avatar list-avatar-lg">{{ market.itemAvatar(selected) }}</span>
              <div class="min-w-0 flex-1">
                <p class="flex flex-wrap items-baseline gap-x-3">
                  <span class="font-mono text-title-l">{{ market.itemTitle(selected) }}</span>
                  <span class="text-title-m text-md-on-surface-variant">{{ market.itemLabel(selected) }}</span>
                </p>
                <div class="mt-1.5 flex flex-wrap gap-2">
                  <span class="badge badge-primary">{{ groupLabel(list.group) }}</span>
                  <span class="badge">{{ market.itemMeta(selected) }}</span>
                  <span class="badge" :class="selected.bars ? 'badge-tertiary' : 'badge-error'">
                    {{ selected.bars ? `本地 ${formatCount(selected.bars)} 根` : '本地无数据' }}
                  </span>
                </div>
              </div>
              <div class="flex flex-wrap gap-1">
                <button type="button" class="btn btn-tonal btn-sm" :disabled="!detail.total || detail.exporting" @click="exportCsv">
                  <MIcon name="download" />{{ detail.exporting ? '导出中…' : '导出 CSV' }}
                </button>
                <button type="button" class="btn btn-sm" :disabled="busy" @click="refetch">
                  <MIcon name="cloud_download" />重新拉取
                </button>
                <button type="button" class="btn btn-sm btn-danger-outlined" :disabled="busy" @click="removeRange">
                  <MIcon name="delete" />删除区间
                </button>
              </div>
            </div>

            <!-- 查询条件 -->
            <form class="flex flex-wrap items-end gap-3 border-t border-md-outline-variant px-5 py-4 sm:px-6"
              @submit.prevent="query">
              <label class="field">起始日期<input v-model="detail.start" class="input w-40" type="date"></label>
              <label class="field">结束日期<input v-model="detail.end" class="input w-40" type="date"></label>
              <label v-if="market.detail.adjust" class="field">复权
                <select v-model="detail.adjust" class="input w-32">
                  <option value="qfq">前复权</option><option value="hfq">后复权</option><option value="raw">不复权</option>
                </select>
              </label>
              <button type="submit" class="btn btn-filled" :disabled="detail.loading"><MIcon name="search" />查询</button>
              <span v-if="market.detail.timeNote" class="ml-auto self-center text-body-s text-md-on-surface-variant">
                <MIcon name="schedule" :size="16" class="align-[-3px]" /> {{ market.detail.timeNote }}
              </span>
            </form>
            <p v-if="detail.error" class="mx-5 mb-4 banner banner-error sm:mx-6"><MIcon name="error" />{{ detail.error }}</p>

            <!-- 表格 -->
            <div class="max-h-[520px] overflow-auto border-t border-md-outline-variant">
              <table class="m3-table">
                <thead>
                  <tr>
                    <th v-for="col in market.detail.columns" :key="col.key" :class="col.kind !== 'time' && 'num'">{{ col.label }}</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-if="detail.loading">
                    <tr v-for="n in 10" :key="`s${n}`">
                      <td :colspan="market.detail.columns.length"><div class="skeleton h-4"></div></td>
                    </tr>
                  </template>
                  <tr v-else-if="!detail.rows.length">
                    <td :colspan="market.detail.columns.length" class="py-12 text-center text-md-on-surface-variant">
                      这个区间没有数据
                    </td>
                  </tr>
                  <tr v-for="(row, index) in detail.rows" v-else :key="index">
                    <td v-for="col in market.detail.columns" :key="col.key" :class="[col.kind !== 'time' && 'num', cellTone(col, row)]">
                      {{ formatCell(col, row) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- 分页 -->
            <div class="flex flex-wrap items-center justify-end gap-2 border-t border-md-outline-variant px-4 py-2">
              <span class="mr-2 text-body-s text-md-on-surface-variant tabular">
                {{ detail.total ? `${rangeStart}–${rangeEnd}，共 ${formatCount(detail.total)} 根` : '共 0 根' }}
              </span>
              <button type="button" class="icon-btn" aria-label="第一页" :disabled="detail.page <= 1 || detail.loading" @click="goPage(1)">
                <MIcon name="first_page" />
              </button>
              <button type="button" class="icon-btn" aria-label="上一页" :disabled="detail.page <= 1 || detail.loading" @click="goPage(detail.page - 1)">
                <MIcon name="chevron_left" />
              </button>
              <span class="text-label-l tabular">{{ detail.page }} / {{ totalPages }}</span>
              <button type="button" class="icon-btn" aria-label="下一页" :disabled="detail.page >= totalPages || detail.loading" @click="goPage(detail.page + 1)">
                <MIcon name="chevron_right" />
              </button>
              <button type="button" class="icon-btn" aria-label="最后一页" :disabled="detail.page >= totalPages || detail.loading" @click="goPage(totalPages)">
                <MIcon name="last_page" />
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </section>

    <!-- ================= 维护 + 日志 ================= -->
    <section class="grid items-start gap-4 lg:grid-cols-[380px_minmax(0,1fr)]">
      <div class="card p-5">
        <div class="flex items-center gap-3">
          <span class="section-icon"><MIcon name="cleaning_services" /></span>
          <div>
            <h2 class="text-title-m">清理与维护</h2>
            <p class="text-body-s text-md-on-surface-variant">{{ market.keepDaysHint }}</p>
          </div>
        </div>
        <label class="field mt-5">保留最近多少天
          <div class="flex gap-2">
            <input v-model.number="maint.keepDays" class="input w-28" type="number" min="1" max="3650">
            <button type="button" class="btn" :disabled="maint.running || busy || !selectedGroups.length" @click="previewCleanup">
              <MIcon name="preview" />预览
            </button>
          </div>
        </label>
        <Transition name="slide-up">
          <div v-if="maint.preview" class="mt-4 rounded-2xl bg-md-surface-container-high p-4">
            <p class="text-body-m">
              {{ maint.preview.cutoff }} 之前共 <strong class="tabular">{{ formatCount(maint.preview.total) }}</strong> 根可清理
            </p>
            <div class="mt-3 flex gap-2">
              <button type="button" class="btn btn-sm btn-danger" :disabled="!maint.preview.total || maint.running" @click="applyCleanup">
                <MIcon name="delete_forever" />执行清理
              </button>
              <button type="button" class="btn btn-sm btn-text" @click="maint.preview = null">取消</button>
            </div>
          </div>
        </Transition>
        <div class="mt-5 border-t border-md-outline-variant pt-4">
          <button type="button" class="btn btn-tonal w-full" :disabled="maint.running || busy" @click="vacuum">
            <MIcon name="compress" />压缩数据库
          </button>
          <p class="mt-2 text-body-s text-md-on-surface-variant">删除大量数据后，压缩可以把空出来的磁盘空间还给系统。</p>
        </div>
      </div>

      <div class="card overflow-hidden">
        <div class="flex items-center gap-3 p-5">
          <span class="section-icon"><MIcon name="receipt_long" /></span>
          <div class="flex-1">
            <h2 class="text-title-m">操作日志</h2>
            <p class="text-body-s text-md-on-surface-variant">最近 10 次同步、清理和修改</p>
          </div>
          <button type="button" class="icon-btn" aria-label="刷新" @click="loadOverview"><MIcon name="refresh" /></button>
        </div>
        <ul v-if="overview?.logs?.length" class="border-t border-md-outline-variant">
          <li v-for="log in overview.logs" :key="log.id" class="log-item">
            <span class="log-icon" :class="`is-${log.status}`"><MIcon :name="statusIcon(log.status)" :size="20" :filled="log.status !== 'running'" /></span>
            <span class="min-w-0 flex-1">
              <span class="flex items-baseline gap-2">
                <span class="text-body-m font-medium">{{ actionLabel(log.action) }}</span>
                <span class="text-body-s text-md-on-surface-variant">{{ statusLabel(log.status) }}</span>
                <span class="ml-auto shrink-0 text-body-s text-md-on-surface-variant tabular">{{ formatTime(log.started_at) }}</span>
              </span>
              <span class="block truncate text-body-s text-md-on-surface-variant" :title="log.message || ''">
                {{ log.message || groupNames(log.boards) }}
              </span>
            </span>
            <span class="shrink-0 text-right text-body-s tabular">
              <span class="block">{{ formatCount(log.rows || 0) }} 根</span>
              <span class="block text-md-on-surface-variant">{{ formatCount(log.requests || 0) }} 次请求</span>
            </span>
          </li>
        </ul>
        <div v-else class="empty-state border-t border-md-outline-variant py-10">
          <p class="text-body-m text-md-on-surface-variant">还没有记录</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref, watch } from 'vue';
import axios from 'axios';
import MIcon from '../../ui/MIcon.vue';
import { useFeedback } from '../../ui/feedback.js';
import { downloadCsv, formatBytes, formatCompact, formatCount, formatPrice, toDateInput } from './format.js';

const props = defineProps({
  market: { type: Object, required: true },
  // 标签页第一次切到时才加载，避免打开数据页就同时请求两个库
  active: { type: Boolean, default: true },
});
const m = props.market;
const { notify, confirm } = useFeedback();
const PAGE_SIZE = 100;
const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'with', label: '有数据' },
  { key: 'without', label: '缺数据' },
];
const QUICK_RANGES = [
  { label: '最近 30 天', days: 30 },
  { label: '最近 60 天', days: 60 },
  { label: '近半年', days: 182 },
  { label: '今年', year: true },
];

const errorText = (e) => e.response?.data?.detail || e.message;
const short = (value) => (value ? String(value).slice(5, 16) : '');
const groupLabel = (key) => m.groups.find((g) => g.key === key)?.label || key;
const groupNames = (keys) => (keys || '').split(',').filter(Boolean).map(groupLabel).join('、') || '—';
const coverage = (group) => (group.pool ? Math.min(100, Math.round((group.items / group.pool) * 100)) : 0);

// ---------------- 概览 ----------------
const overview = ref(null);
const overviewError = ref('');
const overviewLoading = ref(false);
const groupStats = computed(() => m.groups.map((group) => ({
  ...group,
  rows: 0, items: 0, pool: 0, first: null, last: null,
  ...(m.groupStats(overview.value).find((s) => s.key === group.key) || {}),
})));
const facts = computed(() => (overview.value ? m.overviewFacts(overview.value) : []));
const totalRowsText = computed(() => formatCount(groupStats.value.reduce((sum, g) => sum + (g.rows || 0), 0)));

async function loadOverview () {
  overviewLoading.value = true;
  try {
    const { data } = await axios.get(`${m.api}/overview`);
    overview.value = data;
    overviewError.value = '';
    if (data.retention_days) maint.keepDays = data.retention_days;
    // 页面打开时已有同步在跑（例如刷新了页面），接上它的进度
    if (data.active_sync && !sync.running) {
      sync.running = true;
      sync.task = data.active_sync;
      sync.message = data.active_sync.message;
      pollSync(data.active_sync.task_id);
    }
  } catch (e) {
    overviewError.value = errorText(e);
  } finally {
    overviewLoading.value = false;
  }
}

// ---------------- 连通性 ----------------
const connectivity = ref(null);
const pinging = ref(false);
async function checkPing () {
  if (!m.ping) return;
  pinging.value = true;
  try {
    const { data } = await axios.get(m.ping);
    connectivity.value = data;
    if (data.ok) notify(`${m.sourceName} 可以访问`, { tone: 'success', duration: 2500 });
  } catch (e) {
    connectivity.value = { ok: false, status: 'error', message: errorText(e) };
  } finally {
    pinging.value = false;
  }
}

// ---------------- 同步 ----------------
const sync = reactive({ running: false, task: null, message: '', tone: 'info' });
const syncForm = reactive({
  start: '', end: '', minQuoteVolume: 0,
  groups: Object.fromEntries(m.groups.map((g) => [g.key, g.on])),
});
const selectedGroups = computed(() => m.groups.filter((g) => syncForm.groups[g.key]).map((g) => g.key));
let pollTimer = null;

function rangeFor (range) {
  const now = new Date();
  return {
    end: toDateInput(now),
    start: range.year ? `${now.getFullYear()}-01-01` : toDateInput(new Date(now.getTime() - range.days * 86400000)),
  };
}
function isQuickActive (range) {
  const { start, end } = rangeFor(range);
  return syncForm.start === start && syncForm.end === end;
}
function applyQuickRange (range) {
  if (isQuickActive(range)) {
    syncForm.start = '';
    syncForm.end = '';
    return;
  }
  Object.assign(syncForm, rangeFor(range));
}

async function startSync () {
  sync.running = true;
  sync.tone = 'info';
  sync.message = '正在创建同步任务…';
  sync.task = null;
  try {
    const { data } = await axios.post(`${m.api}/sync`, m.syncBody({
      groups: selectedGroups.value,
      start: syncForm.start || null,
      end: syncForm.end || null,
      minQuoteVolume: syncForm.minQuoteVolume,
    }));
    sync.task = { task_id: data.task_id, progress: 0 };
    pollSync(data.task_id);
  } catch (e) {
    sync.running = false;
    sync.tone = 'error';
    sync.message = errorText(e);
  }
}

async function pollSync (taskId) {
  try {
    const { data } = await axios.get(`${m.api}/sync/status/${taskId}`);
    sync.task = data;
    sync.message = data.status === 'failed' && data.error ? data.error.split('\n')[0] : data.message;
    if (['completed', 'failed', 'cancelled'].includes(data.status)) {
      sync.running = false;
      sync.tone = { completed: 'success', failed: 'error', cancelled: 'warn' }[data.status];
      notify(sync.message, { tone: sync.tone });
      await Promise.all([loadOverview(), loadList()]);
      if (selected.value) loadDetail();
      return;
    }
    clearTimeout(pollTimer);
    pollTimer = setTimeout(() => pollSync(taskId), 1500);
  } catch (e) {
    sync.running = false;
    sync.tone = 'error';
    sync.message = errorText(e);
  }
}

async function cancelSync () {
  if (!sync.task?.task_id) return;
  try {
    await axios.post(`${m.api}/sync/cancel/${sync.task.task_id}`);
    sync.message = '已请求停止，等在途请求收口…';
  } catch (e) {
    notify(errorText(e), { tone: 'error' });
  }
}

// ---------------- 清单 ----------------
const list = reactive({
  group: m.groups[0].key, items: [], loading: false, error: '', keyword: '', filter: 'all', sort: m.defaultSort,
});
const visibleCount = ref(300);
const withCount = computed(() => list.items.filter((item) => item.bars > 0).length);
const filterCount = (key) => (key === 'all' ? list.items.length : key === 'with' ? withCount.value : list.items.length - withCount.value);

const filteredItems = computed(() => {
  const keyword = list.keyword.toLowerCase();
  const items = list.items.filter((item) => {
    if (list.filter === 'with' && !item.bars) return false;
    if (list.filter === 'without' && item.bars) return false;
    return !keyword || m.search(item, keyword);
  });
  const sorters = {
    quoteVolume: (a, b) => (b.quoteVolume || 0) - (a.quoteVolume || 0),
    bars: (a, b) => (b.bars || 0) - (a.bars || 0),
    change: (a, b) => Number(b.priceChangePercent || 0) - Number(a.priceChangePercent || 0),
  };
  return sorters[list.sort] ? [...items].sort(sorters[list.sort]) : items;
});
// 一个板块上千只，先渲染前 300 个，滚到底再加载，列表始终流畅
const visibleItems = computed(() => filteredItems.value.slice(0, visibleCount.value));
watch(() => [list.keyword, list.filter, list.sort, list.group], () => { visibleCount.value = 300; });

async function loadList () {
  list.loading = !list.items.length;
  list.error = '';
  try {
    const { data } = await axios.get(m.list.path, { params: { [m.groupParam]: list.group, having: 'all' } });
    list.items = data[m.list.field] || [];
    // 刷新后更新选中项的引用，让根数、日期范围跟着变
    if (selected.value) {
      const fresh = list.items.find((item) => m.itemTitle(item) === selectedId.value);
      if (fresh) selected.value = fresh;
    }
  } catch (e) {
    list.items = [];
    list.error = errorText(e);
  } finally {
    list.loading = false;
  }
}

function switchGroup (group) {
  if (list.group === group) return;
  list.group = group;
  list.items = [];
  loadList();
}

// ---------------- 明细 ----------------
const selected = ref(null);
const selectedId = computed(() => (selected.value ? m.itemTitle(selected.value) : null));
const detail = reactive({
  start: '', end: '', adjust: 'qfq', rows: [], total: 0, page: 1, loading: false, error: '', exporting: false,
});
const totalPages = computed(() => Math.max(1, Math.ceil(detail.total / PAGE_SIZE)));
const rangeStart = computed(() => (detail.total ? (detail.page - 1) * PAGE_SIZE + 1 : 0));
const rangeEnd = computed(() => Math.min(detail.page * PAGE_SIZE, detail.total));

function select (item) {
  selected.value = item;
  const range = m.itemRange(item);
  detail.start = range ? range.first.slice(0, 10) : '';
  detail.end = range ? range.last.slice(0, 10) : '';
  detail.page = 1;
  detail.error = '';
  detail.rows = [];
  detail.total = 0;
  if (range) loadDetail();
}

function detailParams (extra = {}) {
  return {
    [m.detail.idParam]: selectedId.value,
    start: detail.start || undefined,
    end: detail.end || undefined,
    ...(m.detail.adjust ? { adjust: detail.adjust } : {}),
    ...extra,
  };
}

async function loadDetail () {
  if (!selected.value) return;
  detail.loading = true;
  detail.error = '';
  try {
    const { data } = await axios.get(m.detail.path, {
      params: detailParams({ limit: PAGE_SIZE, offset: (detail.page - 1) * PAGE_SIZE }),
    });
    detail.rows = data.rows || [];
    detail.total = data.total || 0;
  } catch (e) {
    detail.rows = [];
    detail.total = 0;
    detail.error = errorText(e);
  } finally {
    detail.loading = false;
  }
}

function query () {
  detail.page = 1;
  loadDetail();
}

function goPage (page) {
  const target = Math.min(Math.max(1, page), totalPages.value);
  if (target === detail.page) return;
  detail.page = target;
  loadDetail();
}

function formatCell (col, row) {
  const value = row[col.key];
  if (col.kind === 'time') return value ? String(value).slice(0, 16) : '—';
  if (col.kind === 'price' || col.kind === 'close') return formatPrice(value, m.detail.priceDigits ?? null);
  if (col.kind === 'compact') return formatCompact(value);
  return formatCount(value);
}

// 收盘价按涨跌着色：A 股习惯红涨绿跌
function cellTone (col, row) {
  if (col.kind !== 'close' || row.open == null || row.close == null) return '';
  return Number(row.close) > Number(row.open) ? 'text-rise' : Number(row.close) < Number(row.open) ? 'text-fall' : '';
}

async function exportCsv () {
  detail.exporting = true;
  try {
    // 导出当前查询的全部结果（上限 5000），不只是当前页
    const { data } = await axios.get(m.detail.path, { params: detailParams({ limit: 5000, offset: 0 }) });
    const rows = data.rows || [];
    if (!rows.length) {
      notify('当前查询没有数据可导出', { tone: 'warn' });
      return;
    }
    const suffix = m.detail.adjust ? `_${detail.adjust}` : '';
    downloadCsv(`${selectedId.value}_${detail.start || 'all'}_${detail.end || 'all'}${suffix}.csv`, m.detail.columns, rows);
    notify(`已导出 ${formatCount(rows.length)} 根 K 线`, { tone: 'success' });
  } catch (e) {
    notify(errorText(e), { tone: 'error' });
  } finally {
    detail.exporting = false;
  }
}

async function refetch () {
  if (!detail.start || !detail.end) {
    notify('重新拉取需要先填起始日期和结束日期', { tone: 'warn' });
    return;
  }
  const ok = await confirm({
    title: `重新拉取 ${selectedId.value}？`,
    message: `从 ${m.sourceName} 重新拉取 ${detail.start} ~ ${detail.end} 的数据，覆盖本地这段区间。`,
    confirmText: '重新拉取', icon: 'cloud_download',
  });
  if (!ok) return;
  maint.running = true;
  try {
    const { data } = await axios.post(`${m.api}/refetch`, m.refetchBody(selectedId.value, detail.start, detail.end));
    notify(`${selectedId.value} 已重新拉取 ${formatCount(data.rows)} 根`, { tone: 'success' });
    detail.page = 1;
    await Promise.all([loadDetail(), loadOverview(), loadList()]);
  } catch (e) {
    notify(errorText(e), { tone: 'error', duration: 8000 });
  } finally {
    maint.running = false;
  }
}

async function removeRange () {
  const ok = await confirm({
    title: `删除 ${selectedId.value} 的本地数据？`,
    message: `将删除 ${detail.start || '最早'} ~ ${detail.end || '最新'} 之间的本地 K 线。删除后可以用「重新拉取」补回。`,
    confirmText: '删除', danger: true, icon: 'delete',
  });
  if (!ok) return;
  maint.running = true;
  try {
    const { data } = await axios.delete(`${m.detail.path}`, {
      params: m.deleteParams(selectedId.value, detail.start || undefined, detail.end || undefined),
    });
    notify(`已删除 ${formatCount(data.deleted)} 根 K 线`, { tone: 'success' });
    detail.rows = [];
    detail.total = 0;
    await Promise.all([loadOverview(), loadList()]);
  } catch (e) {
    notify(errorText(e), { tone: 'error' });
  } finally {
    maint.running = false;
  }
}

// ---------------- 维护 ----------------
const maint = reactive({ keepDays: 60, preview: null, running: false });
const busy = computed(() => sync.running || maint.running);

async function clearGroup (group) {
  const ok = await confirm({
    title: `清空${group.label}？`,
    message: `将删除${group.label}本地全部 ${formatCount(group.rows)} 根 K 线，之后需要重新同步。`,
    confirmText: '清空', danger: true, icon: 'delete_sweep',
  });
  if (!ok) return;
  maint.running = true;
  try {
    const { data } = await axios.delete(m.clearPath(group.key));
    notify(`${group.label}已清空 ${formatCount(data.deleted)} 根`, { tone: 'success' });
    await Promise.all([loadOverview(), loadList()]);
  } catch (e) {
    notify(errorText(e), { tone: 'error' });
  } finally {
    maint.running = false;
  }
}

async function previewCleanup () {
  maint.running = true;
  try {
    const { data } = await axios.post(`${m.api}/cleanup`, {
      [m.groupParam]: selectedGroups.value, keep_days: maint.keepDays, apply: false,
    });
    maint.preview = data;
  } catch (e) {
    notify(errorText(e), { tone: 'error' });
  } finally {
    maint.running = false;
  }
}

async function applyCleanup () {
  const ok = await confirm({
    title: '执行清理？',
    message: `删除 ${maint.preview.cutoff} 之前的 ${formatCount(maint.preview.total)} 根 K 线。`,
    confirmText: '清理', danger: true, icon: 'delete_forever',
  });
  if (!ok) return;
  maint.running = true;
  try {
    const { data } = await axios.post(`${m.api}/cleanup`, {
      [m.groupParam]: selectedGroups.value, keep_days: maint.keepDays, apply: true,
    });
    notify(`已清理 ${formatCount(data.total)} 根过期 K 线`, { tone: 'success' });
    maint.preview = null;
    await Promise.all([loadOverview(), loadList()]);
  } catch (e) {
    notify(errorText(e), { tone: 'error' });
  } finally {
    maint.running = false;
  }
}

async function vacuum () {
  maint.running = true;
  try {
    const { data } = await axios.post(`${m.api}/vacuum`);
    notify(`压缩完成，释放 ${formatBytes(data.freed)}`, { tone: 'success' });
    await loadOverview();
  } catch (e) {
    notify(errorText(e), { tone: 'error' });
  } finally {
    maint.running = false;
  }
}

// ---------------- 日志文案 ----------------
const actionLabel = (action) => ({ sync: '同步', cleanup: '清理', refetch: '重新拉取', delete: '删除', clear: '清空', vacuum: '压缩' })[action] || action;
const statusLabel = (status) => ({ running: '进行中', completed: '完成', cancelled: '已停止', failed: '失败' })[status] || status;
const statusIcon = (status) => ({ running: 'progress_activity', completed: 'check_circle', cancelled: 'do_not_disturb_on', failed: 'error' })[status] || 'info';
const toneIcon = (tone) => ({ success: 'check_circle', error: 'error', warn: 'do_not_disturb_on' })[tone] || 'info';
const formatTime = (value) => (value ? value.replace('T', ' ').slice(5, 16) : '—');

// ---------------- 生命周期 ----------------
let loaded = false;
watch(() => props.active, (active) => {
  if (!active || loaded) return;
  loaded = true;
  loadOverview();
  loadList();
  checkPing();
}, { immediate: true });

onUnmounted(() => clearTimeout(pollTimer));
</script>

<style scoped>
.hero-card {
  border-radius: 28px;
  padding: 20px 22px;
  background: linear-gradient(145deg, var(--md-primary-container), color-mix(in srgb, var(--md-tertiary-container) 70%, var(--md-primary-container)));
  color: var(--md-on-primary-container);
  overflow: hidden;
  min-width: 0;
}
.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
  background: color-mix(in srgb, var(--md-on-primary-container) 10%, transparent);
}
.stat-card {
  border-radius: 24px;
  padding: 18px 20px;
  background: var(--md-surface-container-low);
  min-width: 0;
}
.stat-avatar {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
}
.stat-avatar.tone-0 { background: var(--md-primary-container); color: var(--md-on-primary-container); }
.stat-avatar.tone-1 { background: var(--md-secondary-container); color: var(--md-on-secondary-container); }
.stat-avatar.tone-2 { background: var(--md-tertiary-container); color: var(--md-on-tertiary-container); }
.section-icon {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}
.sync-status {
  margin: 0 20px 20px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--md-surface-container-high);
}
@media (min-width: 640px) { .sync-status { margin: 0 24px 24px; } }
.sync-status.is-success { background: color-mix(in srgb, var(--md-fall) 14%, var(--md-surface-container-high)); }
.sync-status.is-error { background: var(--md-error-container); color: var(--md-on-error-container); }
.sync-status.is-warn { background: var(--md-tertiary-container); color: var(--md-on-tertiary-container); }

.search-field {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 48px;
  padding: 0 16px;
  border-radius: 9999px;
  background: var(--md-surface-container-high);
  transition: box-shadow var(--md-duration-short) var(--md-ease-standard);
}
.search-field:focus-within { box-shadow: inset 0 0 0 2px var(--md-primary); }
.search-field input {
  flex: 1;
  min-width: 0;
  background: transparent;
  outline: none;
  border: 0;
  color: var(--md-on-surface);
}
.search-field input::-webkit-search-cancel-button { display: none; }

.list-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  cursor: pointer;
  isolation: isolate;
  overflow: hidden;
  content-visibility: auto;
  contain-intrinsic-size: auto 64px;
  transition: background-color var(--md-duration-short) var(--md-ease-standard);
}
.list-item:hover { background: color-mix(in srgb, var(--md-on-surface) 6%, transparent); }
.list-item.is-selected { background: var(--md-secondary-container); color: var(--md-on-secondary-container); }
.list-item.is-selected .text-md-on-surface-variant { color: inherit; opacity: 0.8; }
.list-avatar {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 9999px;
  background: var(--md-primary-container);
  color: var(--md-on-primary-container);
  font-weight: 500;
  font-size: 15px;
}
.list-avatar.is-empty { background: var(--md-surface-container-highest); color: var(--md-on-surface-variant); }
.list-avatar-lg { width: 56px; height: 56px; border-radius: 18px; font-size: 22px; }

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding-left: 24px;
  padding-right: 24px;
}
.empty-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 9999px;
  background: var(--md-surface-container-highest);
  color: var(--md-on-surface-variant);
}
.empty-icon-lg {
  width: 96px;
  height: 96px;
  border-radius: 32px;
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
  animation: breathe 3.2s var(--md-ease-standard) infinite;
}
@keyframes breathe {
  50% { border-radius: 48px; transform: scale(1.04); }
}

.log-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 20px;
  border-bottom: 1px solid color-mix(in srgb, var(--md-outline-variant) 60%, transparent);
}
.log-item:last-child { border-bottom: 0; }
.log-icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: var(--md-surface-container-highest);
  color: var(--md-on-surface-variant);
}
.log-icon.is-completed { background: color-mix(in srgb, var(--md-fall) 16%, transparent); color: var(--md-fall); }
.log-icon.is-failed { background: var(--md-error-container); color: var(--md-on-error-container); }
.log-icon.is-running { background: var(--md-primary-container); color: var(--md-on-primary-container); }
.log-icon.is-running :deep(.m-icon) { animation: spin 1s linear infinite; }

.skeleton {
  border-radius: 10px;
  background: linear-gradient(90deg, var(--md-surface-container-high) 25%, var(--md-surface-container-highest) 37%, var(--md-surface-container-high) 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}
@keyframes shimmer { 0% { background-position: 100% 50%; } 100% { background-position: 0 50%; } }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
