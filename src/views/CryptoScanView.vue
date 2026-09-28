<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <FullKlineChart v-model:visible="showFullChart"
      :title="chartStock ? `${chartStock.name}（${chartStock.code}）` : ''"
      :klineData="chartStock ? chartStock.kline_data : []"
      :markLines="chartStock ? chartStock.mark_lines || [] : []" :isDarkMode="isDarkMode"
      :visible-bars="chartBars.full" />

    <div class="mb-6">
      <h1 class="text-xl font-semibold">平台期扫描</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        使用本地 60 分钟行情识别平台期，扫描过程不联网；加密永续和 TradFi 永续分别使用适配阈值。
      </p>
    </div>

    <section class="divide-y divide-border rounded-lg border border-border bg-card" aria-label="扫描设置">
      <div class="p-5 sm:p-6">
        <h2 class="section-title">基础条件</h2>
        <div class="mt-4 space-y-6">
          <div class="base-conditions-primary">
            <div>
              <label for="cu-data-source" class="mb-1 block text-sm font-medium">数据来源</label>
              <select id="cu-data-source" class="input" disabled><option>本地加密行情库</option></select>
              <p class="mt-1.5 text-xs text-muted-foreground">读取已同步的 crypto.db，扫描过程不联网。</p>
            </div>
            <div>
              <ParameterLabel for-id="cu-windows" parameter-id="windows">窗口期</ParameterLabel>
              <div class="seg" role="group" aria-label="窗口期预设">
                <button v-for="preset in WINDOW_PRESETS" :key="preset.name" type="button"
                  :class="['seg-btn', !showCustomWindows && config.windowsInput === preset.value && 'is-active']"
                  :aria-pressed="!showCustomWindows && config.windowsInput === preset.value" :disabled="isScanning"
                  @click="selectPreset(preset.value)">{{ preset.name }}</button>
                <button type="button" :class="['seg-btn', (showCustomWindows || !activePreset) && 'is-active']"
                  :aria-pressed="showCustomWindows || !activePreset" :disabled="isScanning" @click="openCustomWindows">自定义</button>
              </div>
              <div v-if="showCustomWindows" class="mt-2 flex gap-2">
                <input id="cu-windows" v-model="customWindows" class="input" type="text" inputmode="numeric"
                  placeholder="例如 40,80,120" @keydown.enter="applyCustomWindows">
                <button type="button" class="btn-quiet h-10 px-4" @click="applyCustomWindows">确定</button>
              </div>
              <p v-if="windowError" class="mt-1.5 text-xs text-destructive">{{ windowError }}</p>
              <p v-else class="mt-1.5 text-xs text-muted-foreground">
                当前：<span class="font-medium text-foreground">{{ windows.join('、') }}</span> 根 K 线，每个窗口单独判断
              </p>
            </div>
          </div>

          <div class="base-conditions-metrics">
            <div>
              <ParameterLabel for-id="cu-frequency" parameter-id="frequency">数据周期</ParameterLabel>
              <select id="cu-frequency" class="input" disabled><option>60 分钟</option></select>
              <p class="mt-1.5 text-xs text-muted-foreground">固定使用 1 小时 K 线，窗口值按 K 线根数计算。</p>
            </div>
            <div>
              <label for="cu-min-volume" class="mb-1 block text-sm font-medium">24 小时成交额门槛</label>
              <div class="relative">
                <input id="cu-min-volume" v-model.number="config.minQuoteWan" class="input pr-20" type="number"
                  min="0" step="100" :disabled="isScanning">
                <span class="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">万 USDT</span>
              </div>
              <p class="mt-1.5 text-xs text-muted-foreground">设为 0 表示不限；先排除缺少流动性的交易对。</p>
            </div>
            <div>
              <label for="cu-symbols" class="mb-1 block text-sm font-medium">交易对（可选）</label>
              <input id="cu-symbols" v-model.trim="config.symbolInput" class="input" type="text"
                placeholder="BTCUSDT, ETHUSDT" :disabled="isScanning">
              <p class="mt-1.5 text-xs text-muted-foreground">留空扫描全部；多个交易对用逗号或空格分隔。</p>
            </div>
            <div>
              <label for="cu-limit" class="mb-1 block text-sm font-medium">最多返回</label>
              <div class="relative">
                <input id="cu-limit" v-model.number="config.limitCount" class="input pr-10" type="number"
                  min="1" max="5000" placeholder="不限" :disabled="isScanning">
                <span class="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">个</span>
              </div>
              <p class="mt-1.5 text-xs text-muted-foreground">留空返回全部命中结果，按成交额优先。</p>
            </div>
          </div>
        </div>

        <div class="mt-6">
          <span class="mb-1 block text-sm font-medium">扫描类别</span>
          <div class="mt-2 flex flex-wrap gap-2" role="group" aria-label="扫描类别">
            <button v-for="item in CATEGORY_OPTIONS" :key="item.key" type="button"
              :class="['scope-chip', config.categories.includes(item.key) && 'is-selected']"
              :aria-pressed="config.categories.includes(item.key)" :disabled="isScanning" @click="toggleCategory(item.key)">
              <MIcon v-if="config.categories.includes(item.key)" name="check" :size="16" />{{ item.label }}
            </button>
          </div>
          <p class="mt-1.5 text-xs text-muted-foreground">两类市场波动不同；成交量阈值仅在开启成交量分析后显示。</p>
        </div>

        <div class="mt-6 grid gap-5 lg:grid-cols-2">
          <fieldset v-for="category in selectedCategories" :key="category" class="rounded-lg border border-border p-4">
            <legend class="px-1 text-sm font-semibold">{{ categoryLabel(category) }}</legend>
            <div class="mt-1 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div v-for="key in categoryParamKeys" :key="key">
                <label :for="`cu-${category}-${key}`" class="mb-1 block text-xs font-medium">{{ PARAMS[key].label }}</label>
                <input :id="`cu-${category}-${key}`" v-model.number="config.categoryParams[category][key]"
                  class="input h-9" type="number" :step="PARAMS[key].step" :min="PARAMS[key].min"
                  :max="PARAMS[key].max" :disabled="isScanning">
                <p class="mt-1 text-xs text-muted-foreground">{{ PARAMS[key].shortHint }}</p>
              </div>
            </div>
          </fieldset>
        </div>
      </div>

      <div class="p-5 sm:p-6">
        <div class="flex items-baseline justify-between gap-4">
          <h2 class="section-title">功能开关</h2>
          <span class="text-xs text-muted-foreground">已开启 {{ activeFeatures.length }} 项</span>
        </div>
        <div class="mt-4 grid gap-x-10 gap-y-6 md:grid-cols-2">
          <div v-for="column in FEATURE_COLUMNS" :key="column.title">
            <h3 class="text-sm font-medium">{{ column.title }}</h3>
            <p class="mt-0.5 text-xs text-muted-foreground">{{ column.note }}</p>
            <ul class="mt-2 divide-y divide-border">
              <li v-for="key in column.keys" :key="key" class="flex items-start gap-3 py-3">
                <button :id="`cu-sw-${key}`" type="button" role="switch" :aria-checked="config[key]"
                  :aria-describedby="`cu-desc-${key}`" :disabled="isScanning"
                  :class="['switch mt-0.5', config[key] && 'is-on']" @click="toggle(key)">
                  <span class="switch-thumb" aria-hidden="true"></span><span class="sr-only">{{ FEATURES[key].label }}</span>
                </button>
                <div class="min-w-0 flex-1 cursor-pointer" @click="toggle(key)">
                  <div class="text-sm font-medium leading-5">{{ FEATURES[key].label }}</div>
                  <p :id="`cu-desc-${key}`" class="mt-0.5 text-xs text-muted-foreground">{{ FEATURES[key].desc }}</p>
                </div>
                <button type="button" class="help-btn" :aria-label="`查看「${FEATURES[key].label}」详细说明`"
                  title="详细说明" @click="openHelp(key)"><i class="fas fa-circle-question" aria-hidden="true"></i></button>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <div class="p-5 sm:p-6">
        <h2 class="section-title">参数设置</h2>
        <p v-if="!paramBlocks.length" class="mt-2 text-sm text-muted-foreground">开启上方的功能后，可以在这里调整它的参数。</p>
        <div v-else class="mt-4 divide-y divide-border">
          <div v-for="key in paramBlocks" :key="key" class="py-5 first:pt-0 last:pb-0">
            <h3 class="text-sm font-medium">{{ FEATURES[key].label }}</h3>
            <div v-if="key === 'use_window_weights'" class="mt-3">
              <p class="text-xs text-muted-foreground">拖动设置各窗口的相对权重，括号内为归一化后的占比。</p>
              <div class="mt-3 grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                <label v-for="window in windows" :key="window" class="flex items-center gap-3 text-sm">
                  <span class="w-20 shrink-0 tabular-nums">{{ window }} 根 K 线</span>
                  <input v-model.number="weights[window]" type="range" min="0" max="10" step="1" class="min-w-0 flex-1 accent-[var(--primary)]">
                  <span class="w-16 shrink-0 text-right tabular-nums text-muted-foreground">{{ weights[window] }}（{{ Math.round((normalizedWeights[window] || 0) * 100) }}%）</span>
                </label>
              </div>
            </div>
            <div v-else class="mt-3 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
              <div v-for="param in FEATURES[key].params" :key="param">
                <ParameterLabel :for-id="`cu-p-${param}`" :parameter-id="param">{{ PARAMS[param].label }}</ParameterLabel>
                <div class="relative">
                  <input :id="`cu-p-${param}`" v-model.number="config[param]" :class="['input', PARAMS[param].unit && 'pr-10']"
                    type="number" :step="PARAMS[param].step" :min="PARAMS[param].min" :max="PARAMS[param].max" :disabled="isScanning">
                  <span v-if="PARAMS[param].unit" class="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">{{ PARAMS[param].unit }}</span>
                </div>
                <p class="mt-1.5 text-xs text-muted-foreground">{{ PARAMS[param].hint }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="min-w-0 text-sm">
          <p v-if="formError" class="text-destructive" role="alert"><i class="fas fa-circle-exclamation mr-1" aria-hidden="true"></i>{{ formError }}</p>
          <p v-else class="text-muted-foreground">本地加密行情库 · 根 K 线 {{ windows.join('、') }} · 60 分钟 · {{ activeFeatures.length ? `已开启：${activeFeatures.map(key => FEATURES[key].label).join('、')}` : '未开启功能，只按基础条件筛选' }}</p>
        </div>
        <button type="button" class="btn btn-primary h-10 shrink-0 px-6" :disabled="isScanning" @click="startScan">
          <i :class="['fas mr-2', isScanning ? 'fa-spinner fa-spin' : 'fa-magnifying-glass']" aria-hidden="true"></i>{{ isScanning ? '扫描中…' : '开始扫描' }}
        </button>
      </div>
    </section>

    <section ref="resultsRef" class="mt-6 scroll-mt-20 rounded-lg border border-border bg-card" aria-label="扫描结果">
      <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-5 py-4 sm:px-6">
        <h2 class="section-title">扫描结果</h2>
        <p v-if="scan.status !== 'idle' && results.length" class="text-xs text-muted-foreground">
          已发现 {{ results.length }} 个 · {{ categoryOptions.length }} 个类别<span v-if="scan.finishedAt"> · 用时 {{ formatDuration(scan.finishedAt - scan.startedAt) }}</span>
        </p>
        <div class="flex items-center gap-2">
          <label class="text-xs text-muted-foreground" for="cu-history">历史结果</label>
          <select id="cu-history" v-model="selectedHistoryId" class="select h-8 max-w-[22rem] text-xs"
            :disabled="isScanning || historyLoading" @change="loadHistory">
            <option value="">选择历史扫描…</option>
            <option v-for="item in histories" :key="item.history_id" :value="item.history_id">{{ formatHistoryLabel(item) }}</option>
          </select>
        </div>
      </div>

      <div v-if="scan.status === 'running'" class="px-5 py-8 sm:px-6">
        <div class="flex items-baseline justify-between gap-4">
          <p class="text-sm font-medium">正在扫描<span class="font-normal text-muted-foreground"> · 已用时 {{ formatDuration(now - scan.startedAt) }}</span></p>
          <span class="text-sm font-medium tabular-nums">{{ scan.progress }}%</span>
        </div>
        <div class="mt-3 h-2 overflow-hidden rounded-full bg-foreground/[0.08]">
          <div class="h-full origin-left rounded-full bg-primary transition-transform duration-500 ease-out" :style="{ transform: `scaleX(${scan.progress / 100})` }"></div>
        </div>
        <p class="mt-3 text-sm" aria-live="polite">{{ scan.message }}</p>
        <div class="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
          <span v-if="scan.total">已分析 {{ scan.scanned }}/{{ scan.total }} 个 · 发现 {{ scan.found }} 个平台期</span>
          <span v-else>正在读取本地行情，扫描过程不联网</span>
          <button type="button" class="btn-quiet ml-auto h-8 px-4 text-xs" :disabled="cancelRequested" @click="cancelScan">
            <i :class="['fas mr-1.5', cancelRequested ? 'fa-spinner fa-spin' : 'fa-stop']" aria-hidden="true"></i>{{ cancelRequested ? '正在停止扫描…' : '停止扫描' }}
          </button>
        </div>
      </div>

      <div v-else-if="scan.status === 'failed'" class="px-5 py-8 sm:px-6" role="alert">
        <p class="flex items-start gap-2 text-sm font-medium text-destructive"><i class="fas fa-circle-exclamation mt-0.5" aria-hidden="true"></i>{{ scan.message }}</p>
        <details v-if="scan.error" class="mt-3"><summary class="cursor-pointer text-xs text-muted-foreground hover:text-foreground">错误详情</summary><pre class="mt-2 max-h-64 overflow-auto rounded-md bg-foreground/[0.05] p-3 text-xs leading-relaxed">{{ scan.error }}</pre></details>
        <button type="button" class="btn-quiet mt-4 h-9 px-4" @click="startScan">重新扫描</button>
      </div>

      <div v-else-if="scan.status === 'idle' && !results.length" class="px-5 py-12 text-center sm:px-6">
        <p class="text-sm font-medium">还没有扫描结果</p><p class="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">设置好条件后点击「开始扫描」。将直接读取本地加密行情库，不会在扫描过程中联网。</p>
      </div>
      <div v-if="['completed', 'cancelled'].includes(scan.status) && !results.length" class="px-5 py-12 text-center sm:px-6">
        <p class="text-sm font-medium">没有找到符合条件的交易对</p><p class="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">可以放宽对应类别的阈值、关闭部分筛选条件，或换一组窗口期再试。</p>
      </div>

      <template v-if="results.length">
        <div class="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3 sm:px-6">
          <div class="relative w-full sm:w-60">
            <i class="fas fa-magnifying-glass pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground" aria-hidden="true"></i>
            <input v-model.trim="keyword" class="input h-9 pl-8" type="search" placeholder="搜索代码或名称" aria-label="搜索代码或名称">
          </div>
          <select v-model="categoryFilter" class="select" aria-label="按类别筛选">
            <option value="">全部类别（{{ results.length }}）</option>
            <option v-for="item in categoryOptions" :key="item.key" :value="item.key">{{ item.label }}（{{ item.count }}）</option>
          </select>
          <label class="ml-auto flex items-center gap-2 text-xs text-muted-foreground">小图 K 线
            <select v-model.number="chartBars.small" class="select" aria-label="小图 K 线数量">
              <option v-for="count in SMALL_CHART_BAR_OPTIONS" :key="count" :value="count">{{ count }}</option>
            </select>
          </label>
          <label class="flex items-center gap-2 text-xs text-muted-foreground">大图 K 线
            <select v-model.number="chartBars.full" class="select" aria-label="大图 K 线数量">
              <option v-for="count in FULL_CHART_BAR_OPTIONS" :key="count" :value="count">{{ count }}</option>
            </select>
          </label>
          <label class="flex items-center gap-2 text-xs text-muted-foreground">每页
            <select v-model.number="pageSize" class="select"><option :value="12">12</option><option :value="24">24</option><option :value="48">48</option></select>
          </label>
        </div>
        <div v-if="!filteredResults.length" class="px-5 py-12 text-center sm:px-6">
          <p class="text-sm font-medium">没有匹配的交易对</p><button type="button" class="btn-quiet mt-3 h-8 px-3" @click="resetFilters">清除筛选</button>
        </div>
        <div v-else class="grid gap-4 p-4 sm:p-6 lg:grid-cols-2">
          <article v-for="stock in pagedResults" :key="resultKey(stock)" class="flex flex-col rounded-lg border border-border">
            <header class="flex items-start justify-between gap-3 px-4 pt-3">
              <div class="min-w-0">
                <div class="flex items-baseline gap-2"><h3 class="truncate text-base font-semibold">{{ stock.name }}</h3><span class="shrink-0 font-mono text-xs text-muted-foreground">{{ stock.code }}</span></div>
                <span class="chip mt-1">{{ stock.category_label || categoryLabel(stock.category) }}</span>
              </div>
              <div class="flex shrink-0 gap-1.5">
                <button type="button" class="btn-quiet h-8 px-2.5" @click="openChart(stock)"><i class="fas fa-up-right-and-down-left-from-center" aria-hidden="true"></i>大图</button>
                <button type="button" class="btn-quiet h-8 px-2.5" :disabled="!!caseState[resultKey(stock)]" @click="saveToCases(stock)">
                  <i :class="['fas', caseState[resultKey(stock)] === 'saving' ? 'fa-spinner fa-spin' : 'fa-bookmark']" aria-hidden="true"></i>{{ caseState[resultKey(stock)] === 'saved' ? '已存为案例' : caseState[resultKey(stock)] === 'saving' ? '保存中' : '存为案例' }}
                </button>
              </div>
            </header>
            <KlineChart :klineData="latestBars(stock.kline_data, chartBars.small)" :markLines="stock.mark_lines || []" :isDarkMode="isDarkMode" height="200px" width="100%" class="mt-1" />
            <dl class="space-y-1.5 px-4 pb-4 pt-1 text-xs">
              <div class="flex gap-2"><dt class="w-20 shrink-0 font-medium">最新数据</dt><dd class="text-muted-foreground">价格 {{ formatPrice(stock.last_price) }} · 24h 成交额 {{ formatVolume(stock.quote_volume) }}</dd></div>
              <div v-for="row in stock.reasonRows" :key="row.window" class="flex gap-2"><dt class="w-20 shrink-0 font-medium tabular-nums">{{ row.window }} 根 K 线</dt><dd class="text-muted-foreground">{{ row.parts.length ? row.parts.join(' · ') : '满足平台期条件' }}</dd></div>
              <div v-if="stock.commonReasons.length" class="flex gap-2"><dt class="w-20 shrink-0 font-medium">共同</dt><dd class="text-muted-foreground">{{ stock.commonReasons.join(' · ') }}</dd></div>
              <div v-if="stock.weighted_score !== undefined" class="flex gap-2"><dt class="w-20 shrink-0 font-medium">加权得分</dt><dd class="text-muted-foreground">{{ Number(stock.weighted_score).toFixed(3) }}</dd></div>
            </dl>
          </article>
        </div>
        <div v-if="totalPages > 1" class="flex items-center justify-between gap-3 border-t border-border px-5 py-3 text-sm sm:px-6">
          <span class="text-xs text-muted-foreground">第 {{ page }} / {{ totalPages }} 页，共 {{ filteredResults.length }} 个</span>
          <div class="flex gap-2"><button type="button" class="btn-quiet h-8 px-3" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button><button type="button" class="btn-quiet h-8 px-3" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button></div>
        </div>
      </template>
    </section>

    <transition name="fade"><div v-if="notice" :class="['fixed bottom-6 right-6 z-40 max-w-sm rounded-md px-4 py-3 text-sm shadow-lg', notice.type === 'error' ? 'bg-destructive text-destructive-foreground' : 'bg-foreground text-background']" role="status">{{ notice.text }}</div></transition>
  </main>
</template>

<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import axios from 'axios';
import KlineChart from '../components/KlineChart.vue';
import FullKlineChart from '../components/FullKlineChart.vue';
import { latestBars } from '../components/klineWindow.js';
import { ParameterLabel } from '../components/parameter-help';
import MIcon from '../ui/MIcon.vue';

const isDarkMode = inject('isDarkMode');
const parameterHelp = inject('parameterHelp');
const CATEGORY_OPTIONS = [{ key: 'perpetual', label: '加密永续' }, { key: 'tradifi', label: 'TradFi 永续' }];
const WINDOW_PRESETS = [{ name: '标准', value: '40,80,120' }, { name: '短期', value: '20,40,60' }, { name: '中期', value: '60,120,180' }, { name: '长期', value: '120,240,480' }];
const SMALL_CHART_BAR_OPTIONS = [240, 360];
const FULL_CHART_BAR_OPTIONS = [240, 360, 480, 720];
const chartBars = reactive({ small: 240, full: 360 });
const PRICE_CATEGORY_PARAM_KEYS = ['box_threshold', 'ma_diff_threshold', 'volatility_threshold'];
const VOLUME_CATEGORY_PARAM_KEYS = ['volume_change_threshold', 'volume_stability_threshold'];
const PARAMS = {
  box_threshold: { label: '振幅阈值', step: 0.001, min: 0.001, max: 1, shortHint: '窗口最大振幅' },
  ma_diff_threshold: { label: '均线粘合度', step: 0.001, min: 0.001, max: 1, shortHint: '均线最大偏离' },
  volatility_threshold: { label: '波动率阈值', step: 0.001, min: 0.001, max: 1, shortHint: 'K 线波动上限' },
  volume_change_threshold: { label: '成交量变化阈值', step: 0.05, min: 0.01, max: 10, shortHint: '按类别独立标定' },
  volume_stability_threshold: { label: '成交量稳定性阈值', step: 0.05, min: 0.01, max: 10, shortHint: 'TradFi 可大于 1' },
  box_quality_threshold: { label: '箱体质量阈值', step: 0.05, min: 0, max: 1, hint: '箱体最低质量评分，0.6 即 60%' },
  volume_increase_threshold: { label: '成交量突破阈值', step: 0.1, min: 0.1, max: 20, unit: '倍', hint: '放量达到该倍数视为突破' },
  breakthrough_confirmation_days: { label: '确认根数', step: 1, min: 1, max: 50, unit: '根', hint: '突破后需要连续站稳的 K 线根数' },
};
const DEFAULT_PARAMS = {
  perpetual: { box_threshold: 0.15, ma_diff_threshold: 0.01, volatility_threshold: 0.017, volume_change_threshold: 1, volume_stability_threshold: 1.2 },
  tradifi: { box_threshold: 0.04, ma_diff_threshold: 0.003, volatility_threshold: 0.004, volume_change_threshold: 0.6, volume_stability_threshold: 2.3 },
};
const FEATURES = {
  use_box_detection: { label: '箱体检测', desc: '要求形成箱体，并在图上标出支撑位和阻力位', params: ['box_quality_threshold'] },
  use_volume_analysis: { label: '成交量分析', desc: '要求横盘期间缩量、量能平稳；两项基础阈值在类别参数中分别设置', params: ['volume_increase_threshold'] },
  use_breakthrough_prediction: { label: '突破预测', desc: '结合价格与成交量判断可能的突破方向', params: [] },
  use_breakthrough_confirmation: { label: '突破确认', desc: '要求突破后连续站稳，减少假突破', params: ['breakthrough_confirmation_days'] },
  use_window_weights: { label: '窗口权重', desc: '不同窗口按自定义权重合成综合评分', params: [] },
};
const FEATURE_COLUMNS = [
  { title: '形态与量能', note: '控制平台形态本身的约束', keys: ['use_box_detection', 'use_volume_analysis'] },
  { title: '信号与组合', note: '控制突破信号和多窗口合成', keys: ['use_breakthrough_prediction', 'use_breakthrough_confirmation', 'use_window_weights'] },
];
const FEATURE_KEYS = FEATURE_COLUMNS.flatMap(column => column.keys);
const config = reactive({
  categories: ['perpetual', 'tradifi'], symbolInput: '', windowsInput: '40,80,120', minQuoteWan: 0, limitCount: null,
  categoryParams: structuredClone(DEFAULT_PARAMS), use_box_detection: true, box_quality_threshold: 0.6,
  use_volume_analysis: false, volume_increase_threshold: 1.5, use_breakthrough_prediction: false,
  use_breakthrough_confirmation: false, breakthrough_confirmation_days: 1, use_window_weights: false,
});
const categoryParamKeys = computed(() => config.use_volume_analysis
  ? [...PRICE_CATEGORY_PARAM_KEYS, ...VOLUME_CATEGORY_PARAM_KEYS]
  : PRICE_CATEGORY_PARAM_KEYS);
const selectedCategories = computed(() => CATEGORY_OPTIONS.map(item => item.key).filter(key => config.categories.includes(key)));
const categoryLabel = key => CATEGORY_OPTIONS.find(item => item.key === key)?.label || key;
const toggleCategory = key => { config.categories = config.categories.includes(key) ? config.categories.filter(item => item !== key) : [...config.categories, key]; };
const activeFeatures = computed(() => FEATURE_KEYS.filter(key => config[key]));
const paramBlocks = computed(() => activeFeatures.value.filter(key => FEATURES[key].params.length || key === 'use_window_weights'));
const toggle = key => { if (!isScanning.value) config[key] = !config[key]; };
const openHelp = key => parameterHelp?.openTutorial?.(key);

const parseWindows = text => [...new Set(String(text).split(/[,，\s]+/).map(Number).filter(value => Number.isInteger(value) && value >= 10 && value <= 1500))];
const windows = computed(() => parseWindows(config.windowsInput));
const activePreset = computed(() => WINDOW_PRESETS.find(preset => preset.value === config.windowsInput));
const showCustomWindows = ref(false); const customWindows = ref(''); const windowError = ref('');
function selectPreset (value) { config.windowsInput = value; showCustomWindows.value = false; windowError.value = ''; }
function openCustomWindows () { customWindows.value = config.windowsInput; showCustomWindows.value = true; }
function applyCustomWindows () { const parsed = parseWindows(customWindows.value); if (!parsed.length || parsed.length > 5) { windowError.value = '请输入 1 至 5 个 10–1500 的整数窗口，用逗号分隔'; return; } config.windowsInput = parsed.join(','); showCustomWindows.value = false; windowError.value = ''; }

const weights = reactive({});
watch(windows, list => list.forEach(window => { if (weights[window] === undefined) weights[window] = 5; }), { immediate: true });
const normalizedWeights = computed(() => { const total = windows.value.reduce((sum, window) => sum + (weights[window] || 0), 0); return total > 0 ? Object.fromEntries(windows.value.map(window => [window, (weights[window] || 0) / total])) : {}; });
const formError = ref('');
function validate () {
  if (!config.categories.length) return '至少选择一个扫描类别';
  if (!windows.value.length || windows.value.length > 5) return '请设置 1 至 5 个有效窗口期';
  for (const category of config.categories) { const invalid = categoryParamKeys.value.find(key => !Number.isFinite(config.categoryParams[category][key]) || config.categoryParams[category][key] <= 0); if (invalid) return `请填写「${categoryLabel(category)} · ${PARAMS[invalid].label}」`; }
  for (const key of activeFeatures.value.flatMap(feature => FEATURES[feature].params)) if (!Number.isFinite(config[key])) return `请填写「${PARAMS[key].label}」`;
  if (config.minQuoteWan < 0) return '24 小时成交额门槛不能小于 0';
  if (config.limitCount !== null && config.limitCount !== '' && !(Number.isInteger(config.limitCount) && config.limitCount > 0)) return '最多返回应为正整数或留空';
  if (config.use_window_weights && !Object.keys(normalizedWeights.value).length) return '窗口权重之和必须大于 0';
  return '';
}
function buildPayload () {
  const symbols = config.symbolInput.split(/[,，\s]+/).map(value => value.trim().toUpperCase()).filter(Boolean);
  return { categories: [...config.categories], symbols: symbols.length ? symbols : null, windows: windows.value,
    category_params: Object.fromEntries(config.categories.map(category => [category, { ...config.categoryParams[category] }])),
    min_quote_volume: Number(config.minQuoteWan || 0) * 10000, use_box_detection: config.use_box_detection,
    box_quality_threshold: config.box_quality_threshold, use_volume_analysis: config.use_volume_analysis,
    volume_increase_threshold: config.volume_increase_threshold, use_breakthrough_prediction: config.use_breakthrough_prediction,
    use_breakthrough_confirmation: config.use_breakthrough_confirmation, breakthrough_confirmation_days: config.breakthrough_confirmation_days,
    use_window_weights: config.use_window_weights, window_weights: config.use_window_weights ? normalizedWeights.value : {},
    limit_count: config.limitCount === '' || config.limitCount === null ? null : config.limitCount };
}

const scan = reactive({ status: 'idle', progress: 0, message: '', error: '', startedAt: 0, finishedAt: 0, scanned: 0, total: 0, found: 0 });
const isScanning = computed(() => scan.status === 'running');
const results = ref([]); const lastPayload = ref(null); const histories = ref([]); const selectedHistoryId = ref('');
const historyLoading = ref(false); const currentTaskId = ref(null); const cancelRequested = ref(false); const resultsRef = ref(null); const now = ref(Date.now());
let pollTimer = null; let clockTimer = null; let streamCursor = 0;
function resultKey (item) { return `${item?.category || ''}:${item?.code || ''}`; }
function appendResults (items) { if (!Array.isArray(items)) return; const seen = new Set(results.value.map(resultKey)); for (const item of items) if (item?.code && !seen.has(resultKey(item))) { results.value.push(withReasons(item)); seen.add(resultKey(item)); } }
function stopTimers () { clearInterval(pollTimer); clearInterval(clockTimer); pollTimer = clockTimer = null; }
function finish (status, fields = {}) { stopTimers(); streamCursor = 0; cancelRequested.value = false; Object.assign(scan, { status, finishedAt: Date.now(), ...fields }); loadHistories(); }
async function startScan () {
  if (isScanning.value) return; formError.value = validate(); if (formError.value) return;
  const payload = buildPayload(); selectedHistoryId.value = ''; results.value = []; resetFilters(); cancelRequested.value = false; streamCursor = 0;
  Object.assign(scan, { status: 'running', progress: 0, message: '正在提交本地扫描任务…', error: '', startedAt: Date.now(), finishedAt: 0, scanned: 0, total: 0, found: 0 });
  now.value = Date.now(); clockTimer = setInterval(() => { now.value = Date.now(); }, 1000);
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  nextTick(() => resultsRef.value?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' }));
  try { const { data } = await axios.post('/api/crypto/platform/scan/start', payload); lastPayload.value = payload; currentTaskId.value = data.task_id; scan.message = data.message; pollTimer = setInterval(() => poll(data.task_id), 1500); poll(data.task_id); }
  catch (error) { const detail = error.response?.data?.detail; finish('failed', { message: `扫描任务提交失败：${Array.isArray(detail) ? detail.map(item => item.msg).join('；') : (detail || error.message)}` }); }
}
async function poll (taskId) {
  try {
    const { data } = await axios.get(`/api/crypto/platform/scan/status/${taskId}?since=${streamCursor}`);
    Object.assign(scan, { progress: data.progress || 0, message: data.message || '', error: data.error || '', scanned: data.scanned || 0, total: data.total || 0, found: data.found || 0 });
    appendResults(data.new_results); if (typeof data.cursor === 'number') streamCursor = data.cursor;
    if (data.status === 'completed') { results.value = []; appendResults(data.result || []); finish('completed'); }
    else if (data.status === 'cancelled') { results.value = []; appendResults(data.result || data.new_results || []); finish('cancelled', { message: data.message || `扫描已停止，保留 ${results.value.length} 个结果` }); }
    else if (data.status === 'failed') finish('failed', { message: data.message, error: data.error || '' });
  } catch (error) { if (error.response?.status === 404) finish('failed', { message: '扫描任务已丢失（后端可能已重启），请重新扫描' }); }
}
async function cancelScan () { if (!currentTaskId.value || !isScanning.value) return; cancelRequested.value = true; try { await axios.post(`/api/crypto/platform/scan/cancel/${currentTaskId.value}`); scan.message = '正在停止扫描…'; } catch (error) { cancelRequested.value = false; notify(`停止扫描失败：${error.message}`, 'error'); } }

function formatHistoryLabel (item) { const status = item.status === 'cancelled' ? '已停止' : item.status === 'failed' ? '失败' : '完成'; const timestamp = Number(item.created_at || item.saved_at || 0); const createdAt = timestamp > 0 ? new Date(timestamp * 1000).toLocaleString() : '未知时间'; const categories = (item.categories || []).map(categoryLabel).join('、') || '未知类别'; return `${createdAt} · ${categories} · ${status} · ${item.result_count || 0}个`; }
const toTimestampMs = value => { const timestamp = Number(value); return timestamp > 0 ? (timestamp < 1e12 ? timestamp * 1000 : timestamp) : 0; };
async function loadHistories () { try { const { data } = await axios.get('/api/crypto/platform/scan/history'); histories.value = data.histories || []; } catch { histories.value = []; } }
async function loadHistory () {
  if (!selectedHistoryId.value) return; historyLoading.value = true;
  try {
    const { data } = await axios.get(`/api/crypto/platform/scan/history/${selectedHistoryId.value}`); const request = data.request || {};
    if (Array.isArray(request.categories)) config.categories = [...request.categories]; if (Array.isArray(request.windows) && request.windows.length) config.windowsInput = request.windows.join(',');
    if (request.category_params) for (const category of Object.keys(request.category_params)) Object.assign(config.categoryParams[category] || {}, request.category_params[category]);
    config.minQuoteWan = Number(request.min_quote_volume || 0) / 10000; config.symbolInput = (request.symbols || []).join(', ');
    for (const key of FEATURE_KEYS) if (typeof request[key] === 'boolean') config[key] = request[key];
    for (const key of ['box_quality_threshold', 'volume_increase_threshold', 'breakthrough_confirmation_days']) if (request[key] !== undefined) config[key] = request[key];
    config.limitCount = request.limit_count ?? null; results.value = (data.results || []).map(withReasons); lastPayload.value = request;
    Object.assign(scan, { status: data.status === 'cancelled' ? 'cancelled' : data.status === 'failed' ? 'failed' : 'completed', progress: 100,
      scanned: Number(data.scanned || 0), total: Number(data.total || 0), found: results.value.length, message: `已加载历史扫描：${results.value.length} 个交易对`, error: data.error || '',
      startedAt: toTimestampMs(data.created_at), finishedAt: toTimestampMs(data.completed_at || data.saved_at) || Date.now() }); resetFilters();
  } catch (error) { notify(`加载历史结果失败：${error.message}`, 'error'); } finally { historyLoading.value = false; }
}
async function loadDefaults () { try { const { data } = await axios.get('/api/crypto/platform/defaults'); for (const category of data.categories || []) if (config.categoryParams[category.key]) Object.assign(config.categoryParams[category.key], category.params || {}); } catch { /* 内置值与后端保持一致，接口不可用时仍可使用。 */ } }
function formatDuration (ms) { const seconds = Math.max(0, Math.round(ms / 1000)); const minutes = Math.floor(seconds / 60); return minutes ? `${minutes} 分 ${String(seconds % 60).padStart(2, '0')} 秒` : `${seconds} 秒`; }
function splitReason (text) { return String(text).replace(/^\s*\d+\s*根\s*K?线平台期[:：]?\s*/i, '').split(/[,，]\s*(?![^(（]*[)）])/).map(part => part.trim()).filter(Boolean); }
function withReasons (stock) { const rows = Object.entries(stock.selection_reasons || {}).map(([window, text]) => ({ window: Number(window), parts: splitReason(text) })).sort((a, b) => a.window - b.window); let commonReasons = []; if (rows.length > 1) { commonReasons = rows[0].parts.filter(part => rows.every(row => row.parts.includes(part))); rows.forEach(row => { row.parts = row.parts.filter(part => !commonReasons.includes(part)); }); } return { ...stock, reasonRows: rows, commonReasons }; }

const keyword = ref(''); const categoryFilter = ref(''); const pageSize = ref(12); const page = ref(1);
function resetFilters () { keyword.value = ''; categoryFilter.value = ''; page.value = 1; }
const categoryOptions = computed(() => CATEGORY_OPTIONS.map(item => ({ ...item, count: results.value.filter(result => result.category === item.key).length })).filter(item => item.count));
const filteredResults = computed(() => { const value = keyword.value.toLowerCase(); return results.value.filter(item => (!categoryFilter.value || item.category === categoryFilter.value) && (!value || item.code.toLowerCase().includes(value) || item.name.toLowerCase().includes(value))); });
const totalPages = computed(() => Math.max(1, Math.ceil(filteredResults.value.length / pageSize.value)));
const pagedResults = computed(() => filteredResults.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value));
watch([keyword, categoryFilter, pageSize], () => { page.value = 1; });
function goPage (target) { page.value = Math.min(Math.max(1, target), totalPages.value); resultsRef.value?.scrollIntoView({ block: 'start' }); }

const showFullChart = ref(false); const chartStock = ref(null); function openChart (stock) { chartStock.value = stock; showFullChart.value = true; }
const formatPrice = value => value === null || value === undefined || value === '' ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 8 });
const formatVolume = value => { const number = Number(value); if (!Number.isFinite(number)) return '—'; if (number >= 1e8) return `${(number / 1e8).toFixed(2)} 亿 USDT`; if (number >= 1e4) return `${(number / 1e4).toFixed(1)} 万 USDT`; return `${number.toFixed(0)} USDT`; };
const notice = ref(null); let noticeTimer = null;
function notify (text, type = 'info') { notice.value = { text, type }; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { notice.value = null; }, 3000); }
const caseState = reactive({});
async function saveToCases (stock) {
  const key = resultKey(stock); caseState[key] = 'saving';
  try { await axios.post('/api/cases/export', { stockData: { code: stock.code, name: stock.name, industry: stock.category_label || categoryLabel(stock.category) }, analysisResult: { is_platform: true, platform_windows: stock.platform_windows || [], selection_reasons: stock.selection_reasons || {}, parameters: lastPayload.value || buildPayload(), mark_lines: stock.mark_lines || [] }, klineData: stock.kline_data || [] }); caseState[key] = 'saved'; notify(`已存为案例：${stock.name}`); }
  catch (error) { delete caseState[key]; notify(`存为案例失败：${error.message}`, 'error'); }
}
onMounted(() => { loadDefaults(); loadHistories(); });
onUnmounted(() => { stopTimers(); clearTimeout(noticeTimer); });
</script>

<style scoped>
.section-title { @apply text-base font-semibold; }
.base-conditions-primary, .base-conditions-metrics { display: grid; gap: 20px 24px; }
@media (min-width: 640px) { .base-conditions-primary { grid-template-columns: minmax(0, 18rem) minmax(0, 1fr); } .base-conditions-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (min-width: 1024px) { .base-conditions-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.seg { @apply inline-flex flex-wrap gap-1 rounded-md bg-foreground/[0.06] p-1; }
.seg-btn { @apply rounded px-3 py-1 text-sm text-muted-foreground transition-colors duration-150; }
.seg-btn:hover { @apply text-foreground; }
.seg-btn.is-active { @apply bg-card font-medium text-foreground shadow-sm; }
.seg-btn:disabled { @apply cursor-not-allowed opacity-60; }
.switch { @apply relative inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-foreground/20 transition-colors duration-150; }
.switch.is-on { @apply bg-primary; }
.switch:disabled { @apply cursor-not-allowed opacity-40; }
.switch-thumb { @apply inline-block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow transition-transform duration-150; }
.switch.is-on .switch-thumb { @apply translate-x-[18px]; }
.help-btn { @apply -mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-sm text-muted-foreground/70 transition-colors duration-150; }
.help-btn:hover { @apply bg-foreground/5 text-foreground; }
.btn-quiet { @apply inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-border bg-card text-xs font-medium text-foreground transition-colors duration-150; }
.btn-quiet:hover:not(:disabled) { @apply bg-foreground/5; }
.btn-quiet:disabled { @apply cursor-not-allowed opacity-60; }
.chip { @apply inline-block rounded bg-foreground/[0.06] px-1.5 py-0.5 text-xs text-muted-foreground; }
.scope-chip { @apply inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm text-muted-foreground transition-colors; }
.scope-chip:hover:not(:disabled) { @apply bg-foreground/5 text-foreground; }
.scope-chip.is-selected { @apply border-primary bg-primary/10 font-medium text-primary; }
.scope-chip:disabled { @apply cursor-not-allowed opacity-60; }
.select { @apply h-9 rounded-md border border-input bg-background px-2 text-foreground; }
.switch:focus-visible, .seg-btn:focus-visible, .help-btn:focus-visible, .btn-quiet:focus-visible, .select:focus-visible, .scope-chip:focus-visible { @apply outline-none ring-2 ring-ring ring-offset-2 ring-offset-card; }
@media (prefers-reduced-motion: reduce) { .switch, .switch-thumb, .seg-btn { transition: none; } }
</style>
