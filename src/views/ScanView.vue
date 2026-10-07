<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <p v-if="legacyUnitNotice" role="status" class="mb-4 rounded-lg border border-border bg-muted p-3 text-sm">此历史记录使用旧版单位标签。数值已按原有计算含义恢复为 K 线根数；下跌时间范围仍为日历天。再次扫描将使用新版明确单位，原历史记录不变。</p>
    <!-- 完整K线图弹窗 -->
    <FullKlineChart v-if="showFullChart" :kline-url="chartStock?.kline_url" v-model:visible="showFullChart" :title="chartStock ? `${chartStock.name}（${chartStock.code}）` : ''"
      :klineData="chartStock ? chartStock.kline_data : []" :markLines="chartStock ? chartStock.mark_lines || [] : []"
      :isDarkMode="isDarkMode" />

    <div class="mb-6">
      <h1 class="text-xl font-semibold">平台期扫描</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        {{ sourceDescription }}
      </p>
    </div>

    <!-- 扫描设置 -->
    <section class="divide-y divide-border rounded-lg border border-border bg-card" aria-label="扫描设置">
      <!-- 基础条件 -->
      <div class="p-5 sm:p-6">
        <h2 class="section-title">基础条件</h2>
        <div class="mt-4 space-y-6">
          <div class="base-conditions-primary">
            <div>
              <label for="p-data-source" class="mb-1 block text-sm font-medium">数据来源</label>
              <select id="p-data-source" :value="config.data_source" class="input"
                :disabled="isScanning" @change="changeDataSource($event.target.value)">
                <option v-for="option in PLATFORM_SCAN_SOURCES" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <p class="mt-1.5 text-xs text-muted-foreground">{{ sourceHint }}</p>
            </div>

            <div>
              <ParameterLabel for-id="p-windows" parameter-id="windows">窗口期</ParameterLabel>
              <div class="seg" role="group" aria-label="窗口期预设">
                <button v-for="preset in WINDOW_PRESETS" :key="preset.name" type="button"
                  :class="['seg-btn', !showCustomWindows && config.windowsInput === preset.value && 'is-active']"
                  :aria-pressed="!showCustomWindows && config.windowsInput === preset.value"
                  @click="selectPreset(preset.value)">
                  {{ preset.name }}
                </button>
                <button type="button" :class="['seg-btn', (showCustomWindows || !activePreset) && 'is-active']"
                  :aria-pressed="showCustomWindows || !activePreset" @click="openCustomWindows">
                  自定义
                </button>
              </div>
              <div v-if="showCustomWindows" class="mt-2 flex gap-2">
                <input id="p-windows" v-model="customWindows" class="input" type="text" inputmode="numeric"
                  placeholder="例如 30,60,90" @keydown.enter="applyCustomWindows">
                <button type="button" class="btn-quiet h-10 px-4" @click="applyCustomWindows">确定</button>
              </div>
              <p v-if="windowError" class="mt-1.5 text-xs text-destructive">{{ windowError }}</p>
              <p v-else class="mt-1.5 text-xs text-muted-foreground">
                当前：<span class="font-medium text-foreground">{{ windows.join('、') }}</span> {{ windowUnit }}，每个窗口单独判断
              </p>
            </div>
          </div>

          <div class="base-conditions-metrics">
            <div>
              <ParameterLabel for-id="p-frequency" parameter-id="frequency">数据周期</ParameterLabel>
              <select id="p-frequency" v-model="config.frequency" class="input"
                :disabled="isScanning || config.data_source === 'local'">
                <option v-for="option in FREQUENCY_OPTIONS" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <p class="mt-1.5 text-xs text-muted-foreground">{{ frequencyHint }}</p>
            </div>

            <div v-for="key in BASE_PARAMS" :key="key">
              <ParameterLabel :for-id="`p-${key}`" :parameter-id="key">{{ PARAMS[key].label }}</ParameterLabel>
              <input :id="`p-${key}`" v-model.number="config[key]" class="input" type="number" :step="PARAMS[key].step"
                :min="PARAMS[key].min" :max="PARAMS[key].max">
              <p class="mt-1.5 text-xs text-muted-foreground">{{ PARAMS[key].hint }}</p>
            </div>
          </div>
        </div>

        <!-- 板块过滤 -->
        <div class="mt-6">
          <ParameterLabel for-id="markets" parameter-id="markets">扫描范围</ParameterLabel>
          <fieldset class="mt-2 flex flex-wrap gap-2" role="group" aria-labelledby="markets">
            <label v-for="board in BOARDS" :key="board.key" class="flex items-center gap-1.5 text-sm">
              <input type="checkbox" :value="board.key" v-model="config.markets"
                :disabled="isScanning || (config.data_source === 'local' && board.key === 'bj')"
                class="h-4 w-4 rounded border-input accent-primary">
              {{ board.label }}
            </label>
          </fieldset>
          <p class="mt-1.5 text-xs text-muted-foreground">
            {{ config.markets.length ? `将扫描：${config.markets.map(k => BOARDS.find(b => b.key === k)?.label).join('、')}` : '未选择板块，将扫描全市场（约 5000 只，需数分钟）' }}
          </p>
        </div>
      </div>

      <!-- 功能开关：所有开关集中在这里 -->
      <div class="p-5 sm:p-6">
        <div class="flex items-baseline justify-between gap-4">
          <h2 class="section-title">功能开关</h2>
          <span class="text-xs text-muted-foreground">已开启 {{ activeFeatures.length }} 项</span>
        </div>
        <div class="mt-4 grid gap-x-10 gap-y-6 md:grid-cols-2">
          <div v-for="(column, ci) in FEATURE_COLUMNS" :key="ci" class="space-y-6">
            <div v-for="group in column" :key="group.title">
              <h3 class="text-sm font-medium">{{ group.title }}</h3>
              <p class="mt-0.5 text-xs text-muted-foreground">{{ group.note }}</p>
              <ul class="mt-2 divide-y divide-border">
                <li v-for="key in group.keys" :key="key"
                  :class="['flex items-start gap-3 py-3', FEATURES[key].requires && 'pl-6']">
                  <!-- 被上级开关阻断时按「关」显示，上级开启后恢复原来的选择 -->
                  <button :id="`sw-${key}`" type="button" role="switch" :aria-checked="isActive(key)"
                    :aria-describedby="`desc-${key}`" :disabled="isBlocked(key) || isUnavailable(key)"
                    :class="['switch mt-0.5', isActive(key) && 'is-on']" @click="toggle(key)">
                    <span class="switch-thumb" aria-hidden="true"></span>
                    <span class="sr-only">{{ FEATURES[key].label }}</span>
                  </button>
                  <div :class="['min-w-0 flex-1', (isBlocked(key) || isUnavailable(key)) ? 'opacity-50' : 'cursor-pointer']"
                    @click="toggle(key)">
                    <div class="text-sm font-medium leading-5">{{ FEATURES[key].label }}</div>
                    <p :id="`desc-${key}`" class="mt-0.5 text-xs text-muted-foreground">
                      {{ featureDescription(key) }}
                    </p>
                  </div>
                  <button type="button" class="help-btn" :aria-label="`查看「${FEATURES[key].label}」详细说明`"
                    title="详细说明" @click="openHelp(FEATURES[key].help || key)">
                    <i class="fas fa-circle-question" aria-hidden="true"></i>
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <!-- 参数设置：只列出已开启且有参数的功能 -->
      <div class="p-5 sm:p-6">
        <h2 class="section-title">参数设置</h2>
        <p v-if="!paramBlocks.length" class="mt-2 text-sm text-muted-foreground">
          开启上方的功能后，可以在这里调整它的参数。
        </p>
        <div v-else class="mt-4 divide-y divide-border">
          <div v-for="key in paramBlocks" :key="key" class="py-5 first:pt-0 last:pb-0">
            <h3 class="text-sm font-medium">{{ FEATURES[key].label }}</h3>

            <div v-if="key === 'use_window_weights'" class="mt-3">
              <p class="text-xs text-muted-foreground">拖动设置各窗口的相对权重，括号内为归一化后的占比。</p>
              <div class="mt-3 grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                <label v-for="w in windows" :key="w" class="flex items-center gap-3 text-sm">
                  <span class="w-20 shrink-0 tabular-nums">{{ w }} {{ windowUnit }}</span>
                  <input v-model.number="weights[w]" type="range" min="0" max="10" step="1"
                    class="min-w-0 flex-1 accent-[var(--primary)]">
                  <span class="w-16 shrink-0 text-right tabular-nums text-muted-foreground">
                    {{ weights[w] }}（{{ Math.round((normalizedWeights[w] || 0) * 100) }}%）
                  </span>
                </label>
              </div>
            </div>

            <div v-else class="mt-3 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
              <div v-for="p in FEATURES[key].params" :key="p">
                <ParameterLabel :for-id="`p-${p}`" :parameter-id="p">{{ PARAMS[p].label }}</ParameterLabel>
                <div class="relative">
                  <input :id="`p-${p}`" v-model.number="config[p]" :class="['input', PARAMS[p].unit && 'pr-10']"
                    type="number" :step="PARAMS[p].step" :min="PARAMS[p].min" :max="PARAMS[p].max">
                  <span v-if="PARAMS[p].unit"
                    class="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">
                    {{ PARAMS[p].unit }}
                  </span>
                </div>
                <p class="mt-1.5 text-xs text-muted-foreground">{{ PARAMS[p].hint }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 操作栏 -->
      <div class="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="min-w-0 text-sm">
          <p v-if="formError" class="text-destructive" role="alert">
            <i class="fas fa-circle-exclamation mr-1" aria-hidden="true"></i>{{ formError }}
          </p>
          <p v-else class="text-muted-foreground">
            {{ sourceLabel }} ·
            {{ windowUnit }} {{ windows.join('、') }} ·
            {{ frequencyLabel }} ·
            {{ activeFeatures.length ? `已开启：${activeFeatures.map(k => FEATURES[k].label).join('、')}` : '未开启功能，只按基础条件筛选' }}
          </p>
        </div>
        <button type="button" class="btn btn-primary h-10 shrink-0 px-6" :disabled="isScanning" @click="startScan">
          <i :class="['fas mr-2', isScanning ? 'fa-spinner fa-spin' : 'fa-magnifying-glass']" aria-hidden="true"></i>
          {{ isScanning ? '扫描中…' : '开始扫描' }}
        </button>
      </div>
    </section>

    <!-- 扫描结果 -->
    <section ref="resultsRef" class="mt-6 scroll-mt-20 rounded-lg border border-border bg-card" aria-label="扫描结果">
      <HistorySaveStatus :state="historyPersistence.state" @retry="historyPersistence.retry" />
      <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-5 py-4 sm:px-6">
        <h2 class="section-title">扫描结果</h2>
        <p v-if="scan.status !== 'idle' && results.length" class="text-xs text-muted-foreground">
          已发现 {{ results.length }} 只 · {{ industryOptions.length }} 个行业<span v-if="scan.finishedAt"> · 用时 {{ formatDuration(scan.finishedAt - scan.startedAt) }}</span>
        </p>
        <div class="flex items-center gap-2">
          <HistoryLink kind="platform_a" />
          <label class="text-xs text-muted-foreground" for="scan-history">历史结果</label>
          <select id="scan-history" v-model="selectedHistoryId" class="select h-8 max-w-[18rem] text-xs"
            :disabled="isScanning || historyLoading" @change="loadHistory">
            <option value="">选择历史扫描…</option>
            <option v-for="item in histories" :key="item.history_id" :value="item.history_id">
              {{ formatHistoryLabel(item) }}
            </option>
          </select>
        </div>
      </div>

      <!-- 扫描中 -->
      <div v-if="scan.status === 'running'" class="px-5 py-8 sm:px-6">
        <div class="flex items-baseline justify-between gap-4">
          <p class="text-sm font-medium">正在扫描<span class="font-normal text-muted-foreground"> · 已用时 {{ formatDuration(now - scan.startedAt) }}</span></p>
          <span class="text-sm font-medium tabular-nums">{{ scan.progress }}%</span>
        </div>
        <div class="mt-3 h-2 overflow-hidden rounded-full bg-foreground/[0.08]">
          <div class="h-full origin-left rounded-full bg-primary transition-transform duration-500 ease-out"
            :style="{ transform: `scaleX(${scan.progress / 100})` }"></div>
        </div>
        <p class="mt-3 text-sm" aria-live="polite">{{ scan.message }}</p>
        <div class="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
          <span v-if="scan.scanned">已分析 {{ scan.scanned }}/{{ scan.total }} 只 · 发现 {{ scan.found }} 只平台期</span>
          <span v-else>{{ scan.dataSource === 'local' ? '正在读取本地行情，扫描过程不联网' : '旧版扫描正在联网取数，切换页面不会中断' }}</span>
          <button type="button" class="btn-quiet ml-auto h-8 px-4 text-xs" :disabled="cancelRequested" @click="cancelScan">
            <i :class="['fas mr-1.5', cancelRequested ? 'fa-spinner fa-spin' : 'fa-stop']" aria-hidden="true"></i>
            {{ cancelRequested ? '正在停止扫描…' : '停止扫描' }}
          </button>
        </div>
      </div>

      <!-- 失败 -->
      <div v-else-if="scan.status === 'failed'" class="px-5 py-8 sm:px-6" role="alert">
        <p class="flex items-start gap-2 text-sm font-medium text-destructive">
          <i class="fas fa-circle-exclamation mt-0.5" aria-hidden="true"></i>{{ scan.message }}
        </p>
        <details v-if="scan.error" class="mt-3">
          <summary class="cursor-pointer text-xs text-muted-foreground hover:text-foreground">错误详情</summary>
          <pre class="mt-2 max-h-64 overflow-auto rounded-md bg-foreground/[0.05] p-3 text-xs leading-relaxed">{{ scan.error }}</pre>
        </details>
        <button type="button" class="btn-quiet mt-4 h-9 px-4" @click="startScan">重新扫描</button>
      </div>

      <!-- 尚未扫描 -->
      <div v-else-if="scan.status === 'idle' && !results.length" class="px-5 py-12 text-center sm:px-6">
        <p class="text-sm font-medium">还没有扫描结果</p>
        <p class="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">
          {{ config.data_source === 'local'
            ? '设置好条件后点击「开始扫描」。将直接读取本地行情库，不会在扫描过程中联网。'
            : '设置好条件后点击「开始扫描」。旧版模式会联网获取股票列表、行业分类和逐只 K 线。' }}
        </p>
      </div>

      <!-- 无结果 -->
      <div v-if="['completed', 'cancelled'].includes(scan.status) && !results.length" class="px-5 py-12 text-center sm:px-6">
        <p class="text-sm font-medium">没有找到符合条件的股票</p>
        <p class="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">可以放宽阈值、关闭部分筛选条件，或换一组窗口期再试。</p>
      </div>

      <!-- 结果列表 -->
      <template v-if="results.length">
        <div class="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3 sm:px-6">
          <div class="relative w-full sm:w-60">
            <i class="fas fa-magnifying-glass pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground"
              aria-hidden="true"></i>
            <input v-model.trim="keyword" class="input h-9 pl-8" type="search" placeholder="搜索代码或名称"
              aria-label="搜索代码或名称">
          </div>
          <select v-model="industry" class="select" aria-label="按行业筛选">
            <option value="">全部行业（{{ results.length }}）</option>
            <option v-for="item in industryOptions" :key="item.name" :value="item.name">
              {{ item.name }}（{{ item.count }}）
            </option>
          </select>
          <label class="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            每页
            <select v-model.number="pageSize" class="select">
              <option :value="12">12</option>
              <option :value="24">24</option>
              <option :value="48">48</option>
            </select>
          </label>
        </div>

        <div v-if="!filteredResults.length" class="px-5 py-12 text-center sm:px-6">
          <p class="text-sm font-medium">没有匹配的股票</p>
          <button type="button" class="btn-quiet mt-3 h-8 px-3" @click="keyword = ''; industry = ''">清除筛选</button>
        </div>

        <div v-else class="grid gap-4 p-4 sm:p-6 lg:grid-cols-2">
          <article v-for="stock in pagedResults" :key="stock.code" class="flex flex-col rounded-lg border border-border">
            <header class="flex items-start justify-between gap-3 px-4 pt-3">
              <div class="min-w-0">
                <div class="flex items-baseline gap-2">
                  <h3 class="truncate text-base font-semibold">{{ stock.name }}</h3>
                  <span class="shrink-0 font-mono text-xs text-muted-foreground">{{ stock.code }}</span>
                </div>
                <span class="chip mt-1">{{ stock.industry || '未知行业' }}</span>
              </div>
              <div class="flex shrink-0 gap-1.5">
                <button type="button" class="btn-quiet h-8 px-2.5" @click="openChart(stock)">
                  <i class="fas fa-up-right-and-down-left-from-center" aria-hidden="true"></i>大图
                </button>
                <button type="button" class="btn-quiet h-8 px-2.5" :disabled="!!caseState[stock.code]"
                  @click="saveToCases(stock)">
                  <i :class="['fas', caseState[stock.code] === 'saving' ? 'fa-spinner fa-spin' : 'fa-bookmark']"
                    aria-hidden="true"></i>
                  {{ caseState[stock.code] === 'saved' ? '已存为案例' : caseState[stock.code] === 'saving' ? '保存中' : '存为案例' }}
                </button>
              </div>
            </header>

            <KlineChart :kline-url="stock.kline_url" :klineData="stock.kline_data" :markLines="stock.mark_lines || []" :isDarkMode="isDarkMode"
              height="200px" width="100%" class="mt-1" />

            <dl class="space-y-1.5 px-4 pb-4 pt-1 text-xs">
              <div v-for="row in stock.reasonRows" :key="row.window" class="flex gap-2">
                <dt class="w-12 shrink-0 font-medium tabular-nums">{{ row.window }} {{ windowUnit }}</dt>
                <dd class="text-muted-foreground">{{ row.parts.length ? row.parts.join(' · ') : '满足平台期条件' }}</dd>
              </div>
              <div v-if="stock.commonReasons.length" class="flex gap-2">
                <dt class="w-12 shrink-0 font-medium">共同</dt>
                <dd class="text-muted-foreground">{{ stock.commonReasons.join(' · ') }}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div v-if="totalPages > 1"
          class="flex items-center justify-between gap-3 border-t border-border px-5 py-3 text-sm sm:px-6">
          <span class="text-xs text-muted-foreground">第 {{ page }} / {{ totalPages }} 页，共 {{ filteredResults.length }} 只</span>
          <div class="flex gap-2">
            <button type="button" class="btn-quiet h-8 px-3" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
            <button type="button" class="btn-quiet h-8 px-3" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
          </div>
        </div>
      </template>
    </section>

    <!-- 操作提示 -->
    <transition name="fade">
      <div v-if="notice" :class="['fixed bottom-6 right-6 z-40 max-w-sm rounded-md px-4 py-3 text-sm shadow-lg',
        notice.type === 'error' ? 'bg-destructive text-destructive-foreground' : 'bg-foreground text-background']"
        role="status">
        {{ notice.text }}
      </div>
    </transition>
  </main>
</template>

<script setup>
import { defineAsyncComponent } from 'vue';
import HistorySaveStatus from '../components/HistorySaveStatus.vue';
import { useHistoryPersistence } from '../scan/useHistoryPersistence.js';
import { normalizePlatformParams, hasLegacyUnits } from '../scan/semantics.js';
import { useScanPolling, scanStatus, fullRows } from '../scan/useScanPolling.js';
import { historySnapshot } from '../scan/session.js';
import HistoryLink from '../components/HistoryLink.vue';
import { shallowRef, ref, reactive, computed, watch, inject, onMounted, onActivated, onUnmounted, nextTick } from 'vue';
import axios from 'axios';
const KlineChart = defineAsyncComponent(() => import('../components/KlineChart.vue'));
const FullKlineChart = defineAsyncComponent(() => import('../components/FullKlineChart.vue'));
import { ParameterLabel } from '../components/parameter-help';
import { applyPlatformScanSource, PLATFORM_SCAN_SOURCES } from './platformScanSource.js';

const isDarkMode = inject('isDarkMode');
const parameterHelp = inject('parameterHelp');

const WINDOW_PRESETS = [
  { name: '标准', value: '60,80,100' },
  { name: '短期', value: '10,20,30' },
  { name: '中期', value: '30,60,90' },
  { name: '长期', value: '60,120,180' },
  { name: '混合', value: '30,60,120' },
];

const FREQUENCY_OPTIONS = [
  { value: 'd', label: '日线' },
  { value: '60', label: '60 分钟' },
];

const BOARDS = [
  { key: 'sh_main', label: '沪市主板' },
  { key: 'sz_main', label: '深市主板' },
  { key: 'sz_gem', label: '创业板' },
  { key: 'sh_star', label: '科创板' },
  { key: 'bj', label: '北交所' },
];

// 数值参数：名称与帮助系统（parameterHelp.js）一致，hint 只补充单位和含义
const PARAMS = {
  box_threshold: { label: '振幅阈值', step: 0.01, min: 0.01, max: 0.99, hint: '窗口内最大振幅，0.3 即 30%' },
  ma_diff_threshold: { label: '均线粘合度', step: 0.005, min: 0, hint: '均线之间的最大偏离，0.25 即 25%' },
  volatility_threshold: { label: '波动率阈值', step: 0.005, min: 0, hint: '日间波动上限，0.4 即 40%' },
  box_quality_threshold: { label: '箱体质量阈值', step: 0.05, min: 0.1, max: 0.9, hint: '箱体最低质量评分，0.3 即 30%' },
  volume_change_threshold: { label: '成交量变化阈值', step: 0.05, min: 0, hint: '横盘期成交量变化的最大比例' },
  volume_stability_threshold: { label: '成交量稳定性阈值', step: 0.05, min: 0, hint: '横盘期成交量波动的最大程度' },
  volume_increase_threshold: { label: '成交量突破阈值', step: 0.1, min: 1, unit: '倍', hint: '放量达到该倍数视为突破' },
  high_point_lookback_bars: { label: '高点查找范围', step: 1, min: 30, unit: '根', hint: '在最近多少根 K 线内找最高点' },
  decline_period_days: { label: '下跌时间范围', step: 1, min: 30, unit: '日历天', hint: '下跌需发生在最近多少个日历天内' },
  decline_threshold: { label: '下跌幅度阈值', step: 0.05, min: 0.1, max: 0.9, hint: '较高点至少下跌多少，0.3 即 30%' },
  rapid_decline_bars: { label: '快速下跌窗口', step: 1, min: 10, max: 60, unit: '根', hint: '多少根 K 线内完成的下跌算快速下跌' },
  rapid_decline_threshold: { label: '快速下跌幅度阈值', step: 0.05, min: 0.05, max: 0.5, hint: '窗口内至少下跌多少，0.15 即 15%' },
  breakthrough_confirmation_bars: { label: '确认根数', step: 1, min: 1, max: 5, unit: '根', hint: '突破后需要站稳的 K 线根数' },
  revenue_growth_percentile: { label: '营收增长率百分位', step: 0.05, min: 0.1, max: 0.9, hint: '需在行业前 X，0.3 即前 30%' },
  profit_growth_percentile: { label: '净利润增长率百分位', step: 0.05, min: 0.1, max: 0.9, hint: '需在行业前 X，0.3 即前 30%' },
  roe_percentile: { label: 'ROE 百分位', step: 0.05, min: 0.1, max: 0.9, hint: '需在行业前 X，0.3 即前 30%' },
  liability_percentile: { label: '资产负债率百分位', step: 0.05, min: 0.1, max: 0.9, hint: '需在行业后 X，0.3 即负债最低的 30%' },
  pe_percentile: { label: 'PE 百分位', step: 0.05, min: 0.1, max: 0.9, hint: '0.7 即排除行业估值最高的 30%' },
  pb_percentile: { label: 'PB 百分位', step: 0.05, min: 0.1, max: 0.9, hint: '0.7 即排除行业估值最高的 30%' },
  fundamental_years_to_check: { label: '检查年数', step: 1, min: 1, max: 5, unit: '年', hint: '要求连续增长的年数' },
  expected_count: { label: '期望股票数量', step: 1, min: 1, unit: '只', hint: '超出时按行业均衡挑选' },
};
const BASE_PARAMS = ['box_threshold', 'ma_diff_threshold', 'volatility_threshold'];

// 功能开关：requires 表示依赖的上级开关，help 为参数帮助系统里的条目
const FEATURES = {
  use_box_detection: { label: '箱体检测', desc: '要求形成箱体，并在图上标出支撑位和阻力位', params: ['box_quality_threshold'] },
  use_volume_analysis: { label: '成交量分析', desc: '要求横盘期间缩量、量能平稳', params: ['volume_change_threshold', 'volume_stability_threshold', 'volume_increase_threshold'] },
  use_low_position: { label: '低位判断', desc: '要求股价已从高点明显回落', params: ['high_point_lookback_bars', 'decline_period_days', 'decline_threshold'] },
  use_rapid_decline_detection: { label: '快速下跌判断', desc: '要求高点之后出现过短期急跌', requires: 'use_low_position', params: ['rapid_decline_bars', 'rapid_decline_threshold'] },
  use_fundamental_filter: { label: '基本面筛选', desc: '按营收、利润、ROE、负债率和估值的行业排名过滤', params: ['revenue_growth_percentile', 'profit_growth_percentile', 'roe_percentile', 'liability_percentile', 'pe_percentile', 'pb_percentile', 'fundamental_years_to_check'] },
  use_breakthrough_prediction: { label: '突破前兆识别', desc: '标注 MACD、RSI、KDJ、布林带的突破信号', params: [] },
  use_breakthrough_confirmation: { label: '突破确认', desc: '标注突破后是否已经站稳', params: ['breakthrough_confirmation_bars'] },
  use_window_weights: { label: '窗口权重', desc: '按权重给出各窗口的加权得分', params: [] },
  limit_count: { label: '限制结果数量', desc: '只保留指定数量，按行业均衡挑选', params: ['expected_count'], help: 'expected_count' },
};
const FEATURE_COLUMNS = [
  [
    { title: '筛选条件', note: '开启后只保留满足条件的股票', keys: ['use_box_detection', 'use_volume_analysis', 'use_low_position', 'use_rapid_decline_detection', 'use_fundamental_filter'] },
  ],
  [
    { title: '附加标注', note: '只在入选理由里补充信息，不减少结果', keys: ['use_breakthrough_prediction', 'use_breakthrough_confirmation', 'use_window_weights'] },
    { title: '结果输出', note: '关闭时返回全部符合条件的股票', keys: ['limit_count'] },
  ],
];
const FEATURE_KEYS = FEATURE_COLUMNS.flat().flatMap(group => group.keys);

const config = reactive({
  data_source: 'local',
  frequency: '60',
  windowsInput: '60,80,100',
  box_threshold: 0.1,
  ma_diff_threshold: 0.02,
  volatility_threshold: 0.02,
  use_box_detection: true,
  box_quality_threshold: 0.8,
  use_volume_analysis: false,
  volume_change_threshold: 0.5,
  volume_stability_threshold: 0.5,
  volume_increase_threshold: 1.5,
  use_low_position: false,
  high_point_lookback_bars: 365,
  decline_period_days: 180,
  decline_threshold: 0.3,
  use_rapid_decline_detection: true, // 只在低位判断开启时生效
  rapid_decline_bars: 30,
  rapid_decline_threshold: 0.15,
  use_fundamental_filter: false,
  revenue_growth_percentile: 0.3,
  profit_growth_percentile: 0.3,
  roe_percentile: 0.3,
  liability_percentile: 0.3,
  pe_percentile: 0.7,
  pb_percentile: 0.7,
  fundamental_years_to_check: 3,
  use_breakthrough_prediction: false,
  use_breakthrough_confirmation: false,
  breakthrough_confirmation_bars: 1,
  use_window_weights: false,
  limit_count: false,
  expected_count: 10,
  markets: ['sz_gem'], // 板块过滤
});

const isBlocked = (key) => !!FEATURES[key].requires && !config[FEATURES[key].requires];
const isUnavailable = (key) => config.data_source === 'local' && key === 'use_fundamental_filter';
const isActive = (key) => config[key] && !isBlocked(key) && !isUnavailable(key);
const activeFeatures = computed(() => FEATURE_KEYS.filter(isActive));
const paramBlocks = computed(() =>
  activeFeatures.value.filter(key => FEATURES[key].params.length || key === 'use_window_weights'));

function toggle (key) {
  if (!isBlocked(key) && !isUnavailable(key)) config[key] = !config[key];
}

function featureDescription (key) {
  if (isUnavailable(key)) return '本地库不含财务指标；切换到「旧版联网」后可用';
  if (isBlocked(key)) return `需先开启「${FEATURES[FEATURES[key].requires].label}」`;
  return FEATURES[key].desc;
}

function changeDataSource (source) {
  applyPlatformScanSource(config, source);
  formError.value = '';
}

const sourceLabel = computed(() =>
  PLATFORM_SCAN_SOURCES.find(option => option.value === config.data_source)?.label || '本地行情库');
const sourceHint = computed(() => config.data_source === 'local'
  ? '读取已同步的本地 60 分钟行情，扫描过程不联网。'
  : '保留的旧版路径：联网获取股票池、行业和逐只 K 线，用于结果比对。');
const sourceDescription = computed(() => config.data_source === 'local'
  ? '使用本地 60 分钟行情识别平台期，扫描过程不联网；可切换到旧版联网做同参数比对。'
  : '使用保留的旧版 Baostock 联网扫描，方便与本地结果比对。');

function openHelp (id) {
  parameterHelp?.openTutorial?.(id);
}

// ---- 窗口期 ----
const parseWindows = (text) => [...new Set(String(text).split(/[,，\s]+/)
  .map(w => Number(w)).filter(w => Number.isInteger(w) && w > 0))];
const windows = computed(() => parseWindows(config.windowsInput));
const activePreset = computed(() => WINDOW_PRESETS.find(p => p.value === config.windowsInput));
const frequencyLabel = computed(() => FREQUENCY_OPTIONS.find(option => option.value === config.frequency)?.label || '日线');
const windowUnit = computed(() => config.frequency === '60' ? '根 K 线' : '天');
const frequencyHint = computed(() => config.frequency === '60'
  ? (config.data_source === 'local'
      ? '本地模式固定使用 60 分钟 K 线，窗口值按 K 线根数计算。'
      : '窗口值按 60 分钟 K 线根数计算，旧版会逐只联网取数。')
  : '窗口值按交易日计算，沿用现有日线扫描。');
const showCustomWindows = ref(false);
const customWindows = ref('');
const windowError = ref('');

function selectPreset (value) {
  config.windowsInput = value;
  showCustomWindows.value = false;
  windowError.value = '';
}

function openCustomWindows () {
  customWindows.value = config.windowsInput;
  showCustomWindows.value = true;
}

function applyCustomWindows () {
  const parsed = parseWindows(customWindows.value);
  if (!parsed.length) {
    windowError.value = '请输入正整数，用逗号分隔，例如 30,60,90';
    return;
  }
  config.windowsInput = parsed.join(',');
  showCustomWindows.value = false;
  windowError.value = '';
}

// 窗口权重：滑块取 0-10，提交时归一化
const weights = reactive({});
watch(windows, (list) => list.forEach(w => { if (weights[w] === undefined) weights[w] = 5; }), { immediate: true });
const normalizedWeights = computed(() => {
  const total = windows.value.reduce((sum, w) => sum + (weights[w] || 0), 0);
  return total > 0 ? Object.fromEntries(windows.value.map(w => [w, (weights[w] || 0) / total])) : {};
});

// ---- 表单校验与请求参数 ----
const legacyUnitNotice = ref(false);
const formError = ref('');

function validate () {
  if (!windows.value.length) return '请至少设置一个窗口期';
  const keys = [...BASE_PARAMS, ...activeFeatures.value.flatMap(k => FEATURES[k].params)];
  const empty = keys.find(k => typeof config[k] !== 'number' || !Number.isFinite(config[k]));
  if (empty) return `请填写「${PARAMS[empty].label}」`;
  if (config.box_threshold <= 0 || config.box_threshold >= 1) return '振幅阈值应在 0 到 1 之间，例如 0.3 表示 30%';
  if (isActive('limit_count') && !(Number.isInteger(config.expected_count) && config.expected_count >= 1)) {
    return '期望股票数量应为正整数';
  }
  return '';
}

function buildPayload () {
  const { windowsInput, limit_count, expected_count, ...rest } = config;
  return { params_semantics_version: 2,
    ...rest,
    windows: windows.value,
    use_technical_indicators: false,
    window_weights: config.use_window_weights ? normalizedWeights.value : {},
    // null 表示不限制数量
    expected_count: limit_count ? expected_count : null,
    markets: config.markets, // 板块过滤
  };
}

// ---- 扫描任务 ----
const scan = reactive({ status: 'idle', progress: 0, message: '', error: '', startedAt: 0, finishedAt: 0, scanned: 0, total: 0, found: 0, dataSource: 'local' });
const isScanning = computed(() => scan.status === 'running');
const results = shallowRef([]);
const lastPayload = ref(null);
const currentTaskId = ref(null); // 当前扫描任务 ID
const resultsRef = ref(null);
const now = ref(Date.now());
const polling = useScanPolling(poll);
const historyPersistence = useHistoryPersistence(loadHistories);
let clockTimer = null;
let streamCursor = 0; // 边扫边出：记录已拉取到的结果数
const cancelRequested = ref(false);
const histories = ref([]);
const selectedHistoryId = ref('');
const historyLoading = ref(false);

function appendResults (items) {
  if (!Array.isArray(items) || !items.length) return;
  const existing = new Set(results.value.map(stock => stock.code));
  const fresh = items.filter(stock => stock && stock.code && !existing.has(stock.code));
  if (fresh.length) results.value = [...results.value, ...fresh.map(withReasons)];
}

function stopTimers () {
  polling.stop();
  clearInterval(clockTimer);
  clockTimer = null;
}
onUnmounted(stopTimers);

function finish (status, fields = {}) {
  stopTimers();
  streamCursor = 0;
  Object.assign(scan, { status, finishedAt: Date.now(), ...fields });
  loadHistories();
}

async function startScan () {
  if (isScanning.value) return;
  formError.value = validate();
  if (formError.value) return;

  historyPersistence.reset();
  const payload = buildPayload();
  selectedHistoryId.value = '';
  cancelRequested.value = false;
  Object.assign(scan, { status: 'running', progress: 0, message: '正在提交扫描任务…', error: '', startedAt: Date.now(), scanned: 0, total: 0, found: 0, dataSource: payload.data_source });
  now.value = Date.now();
  streamCursor = 0;
  clockTimer = setInterval(() => { now.value = Date.now(); }, 1000);
  results.value = [];
  resetFilters();

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  nextTick(() => resultsRef.value?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' }));

  try {
    const { data } = await axios.post('/api/scan/start', payload);
    lastPayload.value = payload;
    currentTaskId.value = data.task_id;
    scan.message = data.message;
    polling.start(data.task_id);
  } catch (e) {
    finish('failed', { message: `扫描任务提交失败：${e.message}` });
  }
}

async function poll (taskId, context) {
  try {
    const { data } = await scanStatus(`/api/scan/status/${taskId}?since=${streamCursor}`, taskId, context);
    if (!context.current()) return;
    if (['completed', 'cancelled', 'failed'].includes(data.status)) historyPersistence.observe(taskId, data);
    scan.progress = data.progress;
    scan.message = data.message;
    scan.scanned = data.scanned || 0;
    scan.total = data.total || 0;
    scan.found = data.found || 0;
    if (typeof data.cancel_requested === 'boolean') cancelRequested.value = data.cancel_requested;

    // 边扫边出：追加新结果
    appendResults(data.new_results);
    if (typeof data.cursor === 'number') streamCursor = data.cursor;

    if (data.status === 'completed') {
      // 最后一次拉完整结果，确保没遗漏
      results.value = [];
      appendResults(data.result || []);
      finish('completed');
    } else if (data.status === 'failed') {
      finish('failed', { message: data.message, error: data.error || '' });
    } else if (data.status === 'cancelled') {
      results.value = [];
      appendResults(data.result || data.new_results || []);
      finish('cancelled', { message: data.message || `扫描已停止，保留 ${results.value.length} 只已发现股票` });
    }
  } catch (e) {
    if (!context.current()) return;
    if (e.response && e.response.status === 404) {
      finish('failed', { message: '扫描任务已丢失（后端可能已重启），请重新扫描' });
    }
    // 其余错误多为网络抖动，下一轮继续查询
  }
}

async function cancelScan () {
  if (!isScanning.value || !currentTaskId.value) return;
  cancelRequested.value = true;
  try {
    await axios.post(`/api/scan/cancel/${currentTaskId.value}`);
    scan.message = '正在停止扫描…';
  } catch (e) {
    cancelRequested.value = false;
    console.error('停止扫描失败:', e);
  }
}

function formatHistoryLabel (item) {
  const status = item.status === 'cancelled' ? '已停止' : item.status === 'failed' ? '失败' : '完成';
  const frequency = item.frequency === '60' ? '60分钟' : '日线';
  const source = item.data_source === 'local' ? '本地' : '旧版联网';
  const count = Number(item.result_count ?? item.results_count ?? 0);
  const timestamp = Number(item.created_at || item.createdAt);
  const createdAt = Number.isFinite(timestamp) && timestamp > 0
    ? new Date(timestamp * 1000).toLocaleString()
    : (item.created_at || item.createdAt || '未知时间');
  return `${createdAt} · ${source} · ${frequency} · ${status} · ${count}只`;
}

function toTimestampMs (value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return 0;
  return timestamp < 1e12 ? timestamp * 1000 : timestamp;
}

async function loadHistory () {
  if (!selectedHistoryId.value) return;
  historyPersistence.reset();
  historyLoading.value = true;
  try {
    const { data: snapshot } = await axios.get(`/api/history/${encodeURIComponent(selectedHistoryId.value)}`);
    const data = historySnapshot(snapshot);
    legacyUnitNotice.value = hasLegacyUnits(data.params);
    const restoredParams = normalizePlatformParams(data.params);
    for (const key of Object.keys(config)) if (restoredParams[key] !== undefined) config[key] = restoredParams[key];
    const historySource = data.data_source ?? data.parameters?.data_source ?? data.config?.data_source ?? 'baostock';
    changeDataSource(historySource);
    config.frequency = data.frequency === '60' ? '60' : 'd';
    if (Array.isArray(data.windows) && data.windows.length) {
      config.windowsInput = data.windows.join(',');
      showCustomWindows.value = false;
    }
    const snapshotResults = data.results || data.result || [];
    results.value = snapshotResults.map(withReasons);
    lastPayload.value = data.parameters || data.config || null;
    scan.status = data.status === 'cancelled' ? 'cancelled' : data.status === 'failed' ? 'failed' : 'completed';
    scan.progress = 100;
    scan.scanned = Number(data.scanned || 0);
    scan.total = Number(data.total || 0);
    scan.found = Number(data.found ?? results.value.length);
    scan.dataSource = historySource;
    scan.message = `已加载历史扫描：${results.value.length} 只股票`;
    scan.error = data.error || '';
    scan.startedAt = toTimestampMs(data.started_at ?? data.created_at);
    scan.finishedAt = toTimestampMs(data.completed_at ?? data.saved_at) || Date.now();
    resetFilters();
  } catch (e) {
    notify(`加载历史结果失败：${e.message}`, 'error');
  } finally {
    historyLoading.value = false;
  }
}

async function loadHistories () {
  try {
    const { data } = await axios.get('/api/scan/history');
    histories.value = data.histories || data || [];
  } catch (e) {
    histories.value = [];
    console.warn('历史扫描列表加载失败:', e.message);
  }
}

function formatDuration (ms) {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m ? `${m} 分 ${String(s).padStart(2, '0')} 秒` : `${s} 秒`;
}

// ---- 入选理由 ----
// 后端格式："80日平台期: 价格区间0.25, 均线收敛0.02, 低位: 从高点下跌35.20%, ..."
// 去掉窗口前缀后按逗号拆开（括号里的逗号保留），各窗口都有的项合并成「共同」一行
function splitReason (text) {
  return String(text)
    .replace(/^\s*\d+\s*日平台期[:：]?\s*/, '')
    .split(/[,，]\s*(?![^(（]*[)）])/)
    .map(part => part.trim()
      .replace(/([一-龥])(?=-?\d)/g, '$1 ')
      .replace(/(\d)(?=[一-龥])/g, '$1 '))
    .filter(Boolean);
}

function withReasons (stock) {
  const rows = Object.entries(stock.selection_reasons || {})
    .map(([window, text]) => ({ window: Number(window), parts: splitReason(text) }))
    .sort((a, b) => a.window - b.window);
  let commonReasons = [];
  if (rows.length > 1) {
    commonReasons = rows[0].parts.filter(part => rows.every(row => row.parts.includes(part)));
    rows.forEach(row => { row.parts = row.parts.filter(part => !commonReasons.includes(part)); });
  }
  return { ...stock, reasonRows: rows, commonReasons };
}

// ---- 结果筛选与分页 ----
const keyword = ref('');
const industry = ref('');
const pageSize = ref(12);
const page = ref(1);

function resetFilters () {
  keyword.value = '';
  industry.value = '';
  page.value = 1;
}

const industryOptions = computed(() => {
  const counts = {};
  results.value.forEach(s => { const name = s.industry || '未知行业'; counts[name] = (counts[name] || 0) + 1; });
  return Object.entries(counts).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
});

const filteredResults = computed(() => {
  const kw = keyword.value.toLowerCase();
  return results.value.filter(s =>
    (!industry.value || (s.industry || '未知行业') === industry.value) &&
    (!kw || s.code.toLowerCase().includes(kw) || s.name.toLowerCase().includes(kw)));
});
const totalPages = computed(() => Math.max(1, Math.ceil(filteredResults.value.length / pageSize.value)));
const pagedResults = computed(() =>
  filteredResults.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value));
watch([keyword, industry, pageSize], () => { page.value = 1; });

function goPage (target) {
  page.value = Math.min(Math.max(1, target), totalPages.value);
  resultsRef.value?.scrollIntoView({ block: 'start' });
}

// ---- 大图与案例 ----
const showFullChart = ref(false);
const chartStock = shallowRef(null);
watch(showFullChart, visible => { if (!visible) chartStock.value = null; });

function openChart (stock) {
  chartStock.value = stock;
  showFullChart.value = true;
}

const notice = ref(null);
let noticeTimer = null;
function notify (text, type = 'info') {
  notice.value = { text, type };
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { notice.value = null; }, 3000);
}

const caseState = reactive({}); // code -> 'saving' | 'saved'

async function saveToCases (stock) {
  caseState[stock.code] = 'saving';
  const markLines = stock.mark_lines || [];
  const levels = (prefix) => markLines
    .filter(m => m.type === 'horizontal' && String(m.text).startsWith(prefix)).map(m => m.value);
  const analysisResult = {
    is_platform: true,
    platform_windows: Object.keys(stock.selection_reasons || {}).map(Number),
    selection_reasons: stock.selection_reasons || {},
    parameters: lastPayload.value || buildPayload(), // 用发起扫描时的参数，而不是之后改动过的表单
    mark_lines: markLines,
  };
  if (levels('支撑位').length || levels('阻力位').length) {
    analysisResult.box_analysis = { is_box_pattern: true, support_levels: levels('支撑位'), resistance_levels: levels('阻力位') };
  }
  try {
    await axios.post('/api/cases/export', {
      stockData: { code: stock.code, name: stock.name, industry: stock.industry || '未知行业' },
      analysisResult,
      klineData: await fullRows(stock),
    });
    caseState[stock.code] = 'saved';
    notify(`已存为案例：${stock.name}`);
  } catch (e) {
    delete caseState[stock.code];
    notify(`存为案例失败：${e.message}`, 'error');
  }
}

onActivated(loadHistories);
</script>

<style scoped>
.section-title {
  @apply text-base font-semibold;
}

.base-conditions-primary,
.base-conditions-metrics {
  display: grid;
  gap: 20px 24px;
}

@media (min-width: 640px) {
  .base-conditions-primary {
    grid-template-columns: minmax(0, 18rem) minmax(0, 1fr);
  }

  .base-conditions-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1024px) {
  .base-conditions-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.seg {
  @apply inline-flex flex-wrap gap-1 rounded-md bg-foreground/[0.06] p-1;
}

.seg-btn {
  @apply rounded px-3 py-1 text-sm text-muted-foreground transition-colors duration-150;
}

.seg-btn:hover {
  @apply text-foreground;
}

.seg-btn.is-active {
  @apply bg-card font-medium text-foreground shadow-sm;
}

.switch {
  @apply relative inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-foreground/20 transition-colors duration-150;
}

.switch.is-on {
  @apply bg-primary;
}

.switch:disabled {
  @apply cursor-not-allowed opacity-40;
}

.switch-thumb {
  @apply inline-block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform duration-150;
}

.switch.is-on .switch-thumb {
  @apply translate-x-[18px];
}

.help-btn {
  @apply -mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-sm text-muted-foreground/70 transition-colors duration-150;
}

.help-btn:hover {
  @apply bg-foreground/5 text-foreground;
}

.btn-quiet {
  @apply inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-border bg-card text-xs font-medium text-foreground transition-colors duration-150;
}

.btn-quiet:hover:not(:disabled) {
  @apply bg-foreground/5;
}

.btn-quiet:disabled {
  @apply cursor-not-allowed opacity-60;
}

.chip {
  @apply inline-block rounded bg-foreground/[0.06] px-1.5 py-0.5 text-xs text-muted-foreground;
}

.select {
  @apply h-9 rounded-md border border-input bg-background px-2 text-foreground;
}

.switch:focus-visible,
.seg-btn:focus-visible,
.help-btn:focus-visible,
.btn-quiet:focus-visible,
.select:focus-visible {
  @apply outline-none ring-2 ring-ring ring-offset-2 ring-offset-card;
}

@media (prefers-reduced-motion: reduce) {
  .switch,
  .switch-thumb,
  .seg-btn {
    transition: none;
  }
}
</style>
