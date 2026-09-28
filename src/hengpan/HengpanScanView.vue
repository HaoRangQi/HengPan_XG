<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <!-- 完整K线图弹窗 -->
    <FullKlineChart v-model:visible="showFullChart" :title="chartTitle"
      :klineData="chartStock ? chartStock.kline_data : []" :markLines="chartMarkLines" :isDarkMode="isDarkMode" />

    <!-- Hero：一句话说清楚这页干什么，右侧是会动的箱体示意 -->
    <section class="hero rise-in" aria-label="页面说明">
      <div class="relative z-10 min-w-0 flex-1">
        <p class="flex items-center gap-2 text-label-l opacity-80"><MIcon name="crop_free" :size="18" />末端锚定横盘箱体</p>
        <h2 class="mt-2 text-headline-m">找出正在横盘蓄势的股票</h2>
        <p class="mt-2 max-w-2xl text-body-m opacity-85">
          用{{ frequencyLabel }}最新一根 K 线定箱体，再用它之前的 K 线验箱体。宁可漏选，不会错选。
        </p>
        <div class="mt-4 flex flex-wrap gap-2">
          <span class="hero-chip"><MIcon name="rule" :size="16" />{{ config.rules.length }} 组规则</span>
          <span class="hero-chip"><MIcon name="schedule" :size="16" />{{ frequencyLabel }}</span>
          <span class="hero-chip"><MIcon name="grid_view" :size="16" />{{ config.markets.length ? `${config.markets.length} 个板块` : '全部 A 股' }}</span>
          <span class="hero-chip"><MIcon name="database" :size="16" />读本地库，不联网</span>
        </div>
      </div>
      <svg class="hero-art" viewBox="0 0 220 140" aria-hidden="true">
        <rect class="hero-box" x="14" y="34" width="176" height="62" rx="12" />
        <g v-for="(c, i) in HERO_CANDLES" :key="i" class="hero-candle" :style="{ '--i': i }">
          <line :x1="24 + i * 14" :x2="24 + i * 14" :y1="c[0]" :y2="c[1]" />
          <rect :x="20 + i * 14" :y="c[2]" width="8" :height="c[3]" rx="2" :class="i === HERO_CANDLES.length - 1 && 'is-last'" />
        </g>
        <path class="hero-break" d="M190 58 L204 40 L214 30" />
      </svg>
    </section>

    <!-- 扫描设置 -->
    <section class="card mt-6 divide-y divide-md-outline-variant overflow-hidden" aria-label="扫描设置">
      <!-- 箱体规则 -->
      <div class="p-5 sm:p-6">
        <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <h2 class="section-title"><span class="section-icon"><MIcon name="tune" :size="20" /></span>箱体规则</h2>
          <div class="flex items-center gap-3 text-xs">
            <button type="button" class="btn btn-text btn-sm" @click="usePreset"><MIcon name="auto_awesome" :size="18" />用推荐组合</button>
            <button v-if="!isDefaultRules" type="button" class="btn btn-text btn-sm"
              @click="resetRules"><MIcon name="restart_alt" :size="18" />恢复默认</button>
          </div>
        </div>
        <p class="mt-1 text-xs text-muted-foreground">
          最多 {{ MAX_RULES }} 组，一次扫描全部算完。取数只做一次，耗时和请求次数与只扫一组相同。
        </p>

        <div class="mt-4 flex flex-wrap items-center gap-2">
          <select v-model="selectedRuleGroupId" class="select h-9 min-w-40 text-sm" aria-label="我的规则组"
            @change="applySavedRuleGroup">
            <option value="">我的规则组…</option>
            <option v-for="group in savedRuleGroups" :key="group.id" :value="group.id">{{ group.name }}</option>
          </select>
          <button type="button" class="btn-quiet h-9 px-3 text-sm" @click="saveCurrentRuleGroup">
            <MIcon name="bookmark_add" :size="18" />保存当前规则组
          </button>
          <button v-if="selectedRuleGroupId" type="button" class="help-btn" title="删除这个规则组"
            aria-label="删除当前规则组" @click="removeSavedRuleGroup">
            <MIcon name="delete" :size="20" />
          </button>
        </div>

        <div class="mt-4 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-muted-foreground">
                <th class="w-10 pb-2 font-normal">组</th>
                <th class="pb-2 pr-4 font-normal">箱体模式</th>
                <th v-for="[key, field] in visibleFields" :key="key" class="pb-2 pr-4 font-normal">
                  {{ field.label }}<span class="ml-1">（{{ field.unit }}）</span>
                </th>
                <th class="w-10 pb-2"><span class="sr-only">删除</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(rule, index) in config.rules" :key="index" class="border-t border-border">
                <td class="py-2 text-xs text-muted-foreground tabular-nums">{{ index + 1 }}</td>
                <td class="py-2 pr-4">
                  <select v-model="rule.box_type" class="select w-full min-w-[7rem]"
                    :aria-label="`第 ${index + 1} 组 箱体模式`">
                    <option v-for="(item, key) in BOX_TYPES" :key="key" :value="key">{{ item.label }}</option>
                  </select>
                </td>
                <!-- 只在用得到的模式下显示输入框；多组规则模式不同时，用不到的那格留空 -->
                <td v-for="[key, field] in visibleFields" :key="key" class="py-2 pr-4">
                  <input v-if="fieldApplies(rule, key)" v-model.number="rule[key]"
                    class="input h-9 w-full min-w-[6rem]" type="number"
                    :step="field.step" :min="field.min" :max="field.max"
                    :placeholder="field.placeholder || ''"
                    :aria-label="`第 ${index + 1} 组 ${field.label}`">
                  <span v-else class="block text-center text-xs text-muted-foreground/60"
                    :title="`${BOX_TYPES[rule.box_type || 'fixed'].label}模式用不到这一项`">—</span>
                </td>
                <td class="py-2">
                  <button v-if="config.rules.length > 1" type="button" class="help-btn"
                    :aria-label="`删除第 ${index + 1} 组规则`" title="删除这一组" @click="removeRule(index)">
                    <MIcon name="close" :size="20" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <button v-if="config.rules.length < MAX_RULES" type="button" class="btn-quiet mt-3 h-8 px-3"
          @click="addRule">
          <MIcon name="add" :size="18" />添加一组
        </button>

        <details class="mt-5 text-sm">
          <summary class="cursor-pointer text-muted-foreground hover:text-foreground">规则怎么算</summary>
          <ol class="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>固定箱高：末端 K 线振幅 =（最高 − 最低）÷ 收盘。不超过「十字星振幅上限」算十字星，否则算普通 K 线。</li>
            <li>十字星认定在箱顶：中点就是上轨，下轨 = 上轨 ×（1 − 箱体高度）。</li>
            <li>普通 K 线认定在箱体中间：中点就是中轨，上下各延伸半个箱高。</li>
            <li>振幅倍数：不区分十字星，末端 K 线最高价往上、最低价往下，各延伸「振幅倍数」倍的末端振幅（最高 − 最低）作为上下轨，箱高随末端 K 线变化。</li>
            <li>末端之前的「回验根数」根 K 线里，越出箱体的不超过「允许越界」根才入选。末端位置认错时箱体会放偏，套不住历史 K 线，自动淘汰。</li>
            <li>整体口径把影线算进去，是默认标准；实体口径只看开盘价和收盘价，更宽松。两种口径一次算完，结果里可以切换。</li>
          </ol>
        </details>
      </div>

      <!-- 扫描范围 -->
      <div class="p-5 sm:p-6">
        <h2 class="section-title"><span class="section-icon"><MIcon name="travel_explore" :size="20" /></span>扫描范围</h2>
        <div class="mt-4 grid gap-x-8 gap-y-5 md:grid-cols-[18rem_minmax(0,1fr)]">
          <div>
            <label for="hp-frequency" class="mb-1 block text-sm font-medium">数据周期</label>
            <select id="hp-frequency" v-model="config.frequency" class="select w-full">
              <option v-for="option in FREQUENCY_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
            <p class="mt-1.5 text-xs text-muted-foreground">{{ frequencyHint }}</p>
          </div>
          <div>
            <label for="hp-scan-date" class="mb-1 block text-sm font-medium">扫描日</label>
            <div class="flex gap-2">
              <input id="hp-scan-date" v-model="config.scan_date" class="input" type="date" :max="today">
              <button v-if="config.scan_date" type="button" class="btn-quiet h-10 px-3" @click="config.scan_date = ''">清空</button>
            </div>
            <p class="mt-1.5 text-xs text-muted-foreground">
              {{ config.scan_date ? `复盘这一天的${frequencyLabel}状态，必须是交易日` : `留空取最新交易日（上证指数最新${frequencyLabel}数据所属日期）` }}
            </p>
          </div>
          <div class="md:col-span-2">
            <span id="hp-markets" class="mb-1 block text-sm font-medium">板块</span>
            <div class="mt-2 flex flex-wrap gap-2" role="group" aria-labelledby="hp-markets">
              <button v-for="board in BOARDS" :key="board.key" type="button" class="chip"
                :class="config.markets.includes(board.key) && 'is-selected'" :aria-pressed="config.markets.includes(board.key)"
                @click="toggleMarket(board.key)">
                <MIcon v-if="config.markets.includes(board.key)" name="check" />{{ board.label }}
              </button>
            </div>
            <p class="mt-1.5 text-xs text-muted-foreground">{{ marketsHint }}</p>
          </div>
        </div>
      </div>

      <!-- 操作栏 -->
      <div class="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div class="min-w-0 text-sm">
          <p v-if="formError" class="text-destructive" role="alert">
            <MIcon name="error" :size="18" class="mr-1 align-[-4px]" />{{ formError }}
          </p>
          <p v-else class="text-muted-foreground">{{ summaryText }}</p>
        </div>
        <button type="button" class="btn btn-filled btn-lg shrink-0" :disabled="isScanning" @click="startScan">
          <MIcon :name="isScanning ? 'progress_activity' : 'play_arrow'" :class="isScanning && 'animate-spin'" />
          {{ isScanning ? '扫描中…' : '开始扫描' }}
        </button>
      </div>
    </section>

    <!-- 扫描结果 -->
    <section ref="resultsRef" class="card mt-6 scroll-mt-24 overflow-hidden" aria-label="扫描结果">
      <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-5 py-4 sm:px-6">
        <div class="flex items-center gap-2">
          <h2 class="section-title"><span class="section-icon"><MIcon name="insights" :size="20" /></span>扫描结果</h2>
          <span v-if="scan.status !== 'idle'" class="tag tag-primary">{{ scanFrequencyLabel }}</span>
        </div>
        <p v-if="scan.finishedAt && scan.status !== 'running'" class="text-xs text-muted-foreground">
          用时 {{ formatDuration(scan.finishedAt - scan.startedAt) }}
        </p>
        <div class="flex items-center gap-2">
          <label class="text-xs text-muted-foreground" for="hp-history">历史结果</label>
          <select id="hp-history" v-model="selectedHistoryId" class="select h-8 max-w-[28rem] text-xs"
            :disabled="isScanning || historyLoading" @change="loadHistory">
            <option value="">选择历史扫描…</option>
            <option v-for="item in histories" :key="item.history_id" :value="item.history_id">
              {{ formatHistoryLabel(item) }}
            </option>
          </select>
          <input ref="importInput" type="file" accept=".json,application/json" class="hidden" @change="importResults">
          <button type="button" class="btn-quiet h-8 px-3 text-xs" :disabled="isScanning || historyLoading"
            title="打开之前导出的扫描结果文件" @click="importInput.click()">
            <MIcon name="upload_file" :size="18" />导入
          </button>
          <button type="button" class="btn-quiet h-8 px-3 text-xs" :disabled="!canExport"
            title="把本次扫描的规则、统计和全部结果存成一个文件，之后可用「导入」原样打开" @click="exportResults">
            <MIcon name="download" :size="18" />导出
          </button>
        </div>
      </div>

      <!-- 扫描中 -->
      <div v-if="scan.status === 'running'" class="px-5 py-8 sm:px-6">
        <div class="flex items-baseline justify-between gap-4">
          <p class="text-sm font-medium">正在扫描<span class="font-normal text-muted-foreground"> · 已用时 {{ formatDuration(now - scan.startedAt) }}</span></p>
          <span class="text-sm font-medium tabular-nums">{{ scan.progress }}%</span>
        </div>
        <div class="progress-linear mt-3" style="height: 6px">
          <div class="bar" :style="{ width: `${scan.progress}%` }"></div>
        </div>
        <p class="mt-3 text-sm" aria-live="polite">{{ scan.message }}</p>
        <div class="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
          <span v-if="scan.total">已分析 {{ scan.scanned }}/{{ scan.total }} 只 · 命中 {{ results.length }} 只</span>
          <span v-else>准备股票池约需 1 分钟，切换到其他页面不会中断</span>
          <button type="button" class="btn-quiet ml-auto h-8 px-4 text-xs" :disabled="cancelRequested" @click="cancelScan">
            <MIcon :name="cancelRequested ? 'progress_activity' : 'stop_circle'" :size="18" :class="cancelRequested && 'animate-spin'" />
            {{ cancelRequested ? '正在停止扫描…' : '停止扫描' }}
          </button>
        </div>
      </div>

      <!-- 失败 -->
      <div v-else-if="scan.status === 'failed'" class="px-5 py-8 sm:px-6" role="alert">
        <p class="flex items-start gap-2 text-sm font-medium text-destructive">
          <MIcon name="error" :size="20" class="shrink-0" />{{ scan.message }}
        </p>
        <details v-if="scan.error" class="mt-3">
          <summary class="cursor-pointer text-xs text-muted-foreground hover:text-foreground">错误详情</summary>
          <pre class="mt-2 max-h-64 overflow-auto rounded-md bg-foreground/[0.05] p-3 text-xs leading-relaxed">{{ scan.error }}</pre>
        </details>
        <button type="button" class="btn-quiet mt-4 h-9 px-4" @click="startScan">重新扫描</button>
      </div>

      <!-- 尚未扫描 -->
      <div v-else-if="scan.status === 'idle'" class="px-5 py-12 text-center sm:px-6">
        <span class="empty-icon"><MIcon name="query_stats" :size="36" /></span>
        <p class="mt-4 text-title-m">还没有扫描结果</p>
        <p class="mx-auto mt-1 max-w-xl text-sm text-muted-foreground">
          点击「开始扫描」，或在右上角选一次历史扫描。{{ config.frequency === '60' ? '60 分钟模式允许使用数据源最新一根 K 线，盘中结果可能随数据更新变化。' : '日线模式建议收盘并且数据源更新之后再扫，盘中的 K 线还没走完，振幅偏小，会被误判成十字星。' }}
        </p>
      </div>

      <!-- 规则切换 -->
      <div v-if="showRuleTabs" class="border-b border-border px-5 py-3 sm:px-6">
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span class="text-xs text-muted-foreground">规则组</span>
          <div class="seg" role="group" aria-label="规则组">
            <button v-for="rule in scan.rules" :key="rule.id" type="button"
              :class="['seg-btn', activeRuleId === rule.id && 'is-active']" :aria-pressed="activeRuleId === rule.id"
              @click="activeRuleId = rule.id">
              {{ ruleLabel(rule) }}
              <span class="ml-1 tabular-nums">{{ ruleCount(rule.id) }}</span>
            </button>
          </div>
          <label class="flex items-center gap-1.5 text-xs text-muted-foreground"
            title="放宽的规则组里本来就含着严格组选出的股票。勾上之后，每只股票只归到第一个命中它的组，后面的组只剩自己新捞出来的。把严格的组排在前面，效果最好。">
            <input v-model="exclusiveOnly" type="checkbox" class="h-4 w-4 rounded border-input accent-primary">
            只看本组新增（{{ ruleCount(activeRuleId, basis, true) }}）
          </label>
          <span class="text-xs text-muted-foreground">{{ activeRuleDetail }}</span>
        </div>
      </div>

      <!-- 统计 -->
      <template v-if="showStats">
        <dl class="grid grid-cols-2 gap-3 border-b border-md-outline-variant p-4 sm:grid-cols-3 sm:p-6 lg:grid-cols-7">
          <div v-for="(tile, i) in statTiles" :key="tile.label" class="stat-tile rise-in" :style="{ '--i': i }">
            <dt class="text-label-m text-md-on-surface-variant">{{ tile.label }}</dt>
            <dd class="mt-1 text-title-l tabular">{{ tile.value }}</dd>
            <dd v-if="tile.note" class="mt-1 text-body-s text-md-on-surface-variant">{{ tile.note }}</dd>
          </div>
        </dl>
        <p v-if="scan.stats && scan.stats.truncated" class="border-b border-border px-5 py-2.5 text-xs text-destructive sm:px-6"
          role="alert">
          <MIcon name="warning" :size="16" class="mr-1 align-[-3px]" />
          命中数超过返回上限，另有 {{ scan.stats.truncated }} 只没有返回（统计数字仍是完整的）。把规则收紧一些再扫可以看到全部。
        </p>
        <p v-if="staleWarning" class="border-b border-border px-5 py-2.5 text-xs text-destructive sm:px-6" role="alert">
          <MIcon name="warning" :size="16" class="mr-1 align-[-3px]" />超过一半的股票在扫描日没有{{ frequencyLabel }}数据，可能是数据源还没更新完，建议晚些再扫。
        </p>
      </template>

      <!-- 无结果 -->
      <div v-if="(scan.status === 'completed' || scan.status === 'cancelled') && !results.length"
        class="px-5 py-12 text-center sm:px-6">
        <span class="empty-icon"><MIcon name="search_off" :size="36" /></span>
        <p class="mt-4 text-title-m">没有找到处在横盘箱体里的股票</p>
        <p class="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">
          几组规则都没有出票。箱体高度或振幅倍数越小、回验根数越多越严格，可以再放宽一些，或换一个扫描日再试。
        </p>
      </div>

      <!-- 结果列表 -->
      <template v-if="results.length">
        <p class="border-b border-border px-5 py-2.5 text-xs text-muted-foreground sm:px-6">
          {{ averageWindowLabel }}成交额分布（{{ BASIS[basis].label }}）：
          <template v-for="(bucket, i) in amountBuckets" :key="bucket.label">
            {{ i ? ' · ' : '' }}{{ bucket.label }} <span class="font-medium text-foreground">{{ bucket.count }}</span>
          </template>
        </p>

        <div class="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3 sm:px-6">
          <div class="seg" role="group" aria-label="越界口径">
            <button v-for="(item, key) in BASIS" :key="key" type="button" :title="item.desc"
              :class="['seg-btn', basis === key && 'is-active']" :aria-pressed="basis === key" @click="basis = key">
              {{ item.label }} {{ ruleCount(activeRuleId, key) }}
            </button>
          </div>
          <div v-if="!isAmplitudeRule" class="seg" role="group" aria-label="命中模式">
            <button v-for="option in MODE_FILTERS" :key="option.value" type="button"
              :class="['seg-btn', modeFilter === option.value && 'is-active']" :aria-pressed="modeFilter === option.value"
              @click="modeFilter = option.value">
              {{ option.label }} {{ modeCount(option.value) }}
            </button>
          </div>
          <div class="relative w-full sm:w-44">
            <MIcon name="search" :size="18" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-md-on-surface-variant" />
            <input v-model.trim="keyword" class="input h-9 pl-8" type="search" placeholder="搜索代码或名称"
              aria-label="搜索代码或名称">
          </div>
          <select v-model="industry" class="select" aria-label="按行业筛选">
            <option value="">全部行业（{{ basisResults.length }}）</option>
            <option v-for="item in industryOptions" :key="item.name" :value="item.name">
              {{ item.name }}（{{ item.count }}）
            </option>
          </select>
          <label class="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input v-model="hideSt" type="checkbox" class="h-4 w-4 rounded border-input accent-primary">隐藏 ST
          </label>
          <div class="ml-auto flex items-center gap-2">
            <select v-model="sortBy" class="select" aria-label="排序方式">
              <option v-for="(item, key) in SORTS" :key="key" :value="key">{{ item.label }}</option>
            </select>
            <select v-model.number="pageSize" class="select" aria-label="每页只数">
              <option :value="12">每页 12</option>
              <option :value="24">每页 24</option>
              <option :value="48">每页 48</option>
            </select>
          </div>
        </div>

        <div v-if="!filteredResults.length" class="px-5 py-12 text-center sm:px-6">
          <p class="text-sm font-medium">这一组规则下没有匹配的股票</p>
          <button v-if="basis === 'full' && !basisResults.length && ruleCount(activeRuleId, 'body')" type="button"
            class="btn-quiet mt-3 h-8 px-3" @click="basis = 'body'">
            切换到实体口径（{{ ruleCount(activeRuleId, 'body') }} 只）
          </button>
          <button v-else type="button" class="btn-quiet mt-3 h-8 px-3" @click="clearFilters">清除筛选</button>
        </div>

        <div v-else class="grid gap-4 p-4 sm:p-6 lg:grid-cols-2">
          <article v-for="(stock, i) in pagedResults" :key="stock.code" class="result-card lift rise-in" :style="{ '--i': i }">
            <header class="flex items-start justify-between gap-3 px-4 pt-3">
              <div class="min-w-0">
                <div class="flex items-baseline gap-2">
                  <h3 class="truncate text-title-m">{{ stock.name }}</h3>
                  <span class="shrink-0 font-mono text-xs text-muted-foreground">{{ stock.code }}</span>
                </div>
                <div class="mt-1 flex flex-wrap gap-1.5">
                  <span :class="['tag', stock.match.mode === 'doji' && 'tag-primary']">
                    {{ MODES[stock.match.mode].label }}
                  </span>
                  <span class="tag">{{ stock.industry || '未知行业' }}</span>
                  <span v-if="stock.is_st" class="tag tag-danger">ST</span>
                  <span v-if="!stock.match.passed_full" class="tag">仅实体口径入选</span>
                  <span v-if="stock.otherRules.length" class="tag" :title="`同时命中：${stock.otherRules.join('、')}`">
                    另命中 {{ stock.otherRules.length }} 组
                  </span>
                </div>
              </div>
              <button type="button" class="btn-quiet h-8 shrink-0 px-2.5" @click="openChart(stock)">
                <MIcon name="open_in_full" :size="16" />大图
              </button>
            </header>

            <KlineChart :klineData="stock.kline_data" :markLines="stock.markLines" :isDarkMode="isDarkMode"
              height="200px" width="100%" class="mt-1" />

            <dl class="grid grid-cols-2 gap-x-4 gap-y-2 px-4 pb-4 pt-1 text-xs sm:grid-cols-3">
              <div>
                <dt class="text-muted-foreground">箱体</dt>
                <dd class="mt-0.5 font-medium">
                  {{ fmtPrice(stock.match.lower) }} – {{ fmtPrice(stock.match.upper) }}
                  <span class="text-muted-foreground">
                    · <template v-if="stock.match.mode === 'amplitude'">箱高 {{ fmtPct(boxHeight(stock.match)) }} · </template>实际震荡 {{ fmtPct(stock.match.actual_range) }}
                  </span>
                </dd>
              </div>
              <div>
                <dt class="text-muted-foreground">收盘 · 末端振幅</dt>
                <dd class="mt-0.5 font-medium">{{ fmtPrice(stock.close) }} · {{ fmtPct(stock.amplitude) }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">越界根数</dt>
                <dd class="mt-0.5 font-medium">整体 {{ stock.match.breach_full }} · 实体 {{ stock.match.breach_body }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">{{ averageWindowLabel }}成交额</dt>
                <dd class="mt-0.5 font-medium">{{ fmtAmount(stock.match.avg_amount) }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">{{ averageWindowLabel }}换手率</dt>
                <dd class="mt-0.5 font-medium">{{ fmtTurn(stock.match.avg_turn) }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">回验起点</dt>
                <dd class="mt-0.5 font-medium">{{ stock.match.lookback_start || '—' }}</dd>
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
      <div v-if="notice" :class="['fixed bottom-24 left-1/2 z-40 max-w-md -translate-x-1/2 rounded-lg px-4 py-3 text-body-m shadow-md-3 lg:bottom-6',
        notice.type === 'error' ? 'bg-md-error-container text-md-on-error-container' : 'bg-md-inverse-surface text-md-inverse-on-surface']"
        role="status">
        {{ notice.text }}
      </div>
    </transition>
  </main>
</template>

<script setup>
import { ref, reactive, computed, watch, inject, onMounted, onUnmounted, nextTick } from 'vue';
import axios from 'axios';
import KlineChart from '../components/KlineChart.vue';
import FullKlineChart from '../components/FullKlineChart.vue';
import {
  createDefaultHengpanConfig,
  deleteRuleGroup,
  loadRuleGroups,
  saveRuleGroup,
} from './ruleGroups.js';

const isDarkMode = inject('isDarkMode');

const API = '/api/hengpan/scan';
const MAX_RULES = 6;
// Hero 插图：一段横盘震荡的 K 线，[影线上端, 影线下端, 实体上沿, 实体高度]，最后一根是收窄的末端 K 线
const HERO_CANDLES = [
  [44, 86, 52, 24], [48, 84, 56, 20], [42, 80, 50, 22], [50, 88, 58, 22], [46, 82, 54, 18], [44, 86, 50, 28],
  [48, 84, 58, 18], [42, 82, 52, 22], [50, 86, 56, 24], [46, 80, 54, 18], [44, 84, 52, 24], [56, 72, 60, 8],
];

// Baostock 没有北交所数据，这里不列北交所
const BOARDS = [
  { key: 'sh_main', label: '沪市主板' },
  { key: 'sz_main', label: '深市主板' },
  { key: 'sz_gem', label: '创业板' },
  { key: 'sh_star', label: '科创板' },
];
const FREQUENCY_OPTIONS = [
  { value: '60', label: '60 分钟 K 线（默认）' },
  { value: 'd', label: '日线' },
];

// 箱体模式：固定箱高按十字星 / 普通 K 线锚定；振幅倍数按末端 K 线的振幅定箱体，不区分十字星
const BOX_TYPES = {
  fixed: { label: '固定箱高' },
  amplitude: { label: '振幅倍数' },
};
// 规则字段：界面上按百分数填写，提交时换算成小数；only 表示只在这种箱体模式下生效
const RULE_FIELDS = {
  doji_pct: { label: '十字星振幅上限', unit: '%', step: 0.1, min: 0.1, max: 5, only: 'fixed' },
  box_pct: { label: '箱体高度', unit: '%', step: 0.5, min: 0.5, max: 30, only: 'fixed' },
  amp_multiple: { label: '振幅倍数', unit: '倍', step: 0.1, min: 0.1, max: 20, only: 'amplitude' },
  max_amp_pct: { label: '振幅上限', unit: '%', step: 0.5, min: 0.1, max: 100, only: 'amplitude',
                 optional: true, placeholder: '不限' },
  lookback: { label: '回验根数', unit: '根', step: 1, min: 10, max: 250 },
  max_breach: { label: '允许越界', unit: '根', step: 1, min: 0, max: 20 },
};
// 默认即方案文档第 10 节的参数表
const DEFAULT_RULE = { box_type: 'fixed', doji_pct: 0.5, box_pct: 4, amp_multiple: 1, max_amp_pct: null, lookback: 80, max_breach: 2 };
// 推荐组合：从文档原版到明显放宽，实测这组梯度在全市场分别出票约 0、10、25、130 只
const PRESET_RULES = [
  { doji_pct: 0.5, box_pct: 4, lookback: 80, max_breach: 2 },
  { doji_pct: 0.5, box_pct: 6, lookback: 40, max_breach: 2 },
  { doji_pct: 0.5, box_pct: 8, lookback: 40, max_breach: 2 },
  { doji_pct: 0.5, box_pct: 10, lookback: 40, max_breach: 2 },
];

const MODES = {
  doji: { label: '十字星 · 贴箱顶' },
  normal: { label: '普通 · 箱体中部' },
  amplitude: { label: '振幅模式' },
};
const BASIS = {
  full: { label: '整体口径', desc: '影线越出箱体也算越界（默认标准）' },
  body: { label: '实体口径', desc: '只看开盘价和收盘价，影线刺破不算' },
};
const MODE_FILTERS = [
  { value: '', label: '全部' },
  { value: 'doji', label: '十字星' },
  { value: 'normal', label: '普通' },
];
// 默认顺序：整体口径入选的在前，其中十字星在前，再按越界根数从少到多
const SORTS = {
  default: {
    label: '默认排序',
    compare: (a, b) => (b.match.passed_full - a.match.passed_full) ||
      ((a.match.mode === 'doji' ? 0 : 1) - (b.match.mode === 'doji' ? 0 : 1)) ||
      (a.match.breach_full - b.match.breach_full) || a.code.localeCompare(b.code),
  },
  matches: { label: '命中组数从多到少', compare: (a, b) => b.otherRules.length - a.otherRules.length },
  amount: { label: '成交额从高到低', compare: (a, b) => (b.match.avg_amount ?? -1) - (a.match.avg_amount ?? -1) },
  turn: { label: '换手率从高到低', compare: (a, b) => (b.match.avg_turn ?? -1) - (a.match.avg_turn ?? -1) },
};
const AMOUNT_BUCKETS = [
  { label: '1000 万以下', max: 1e7 },
  { label: '1000 万–5000 万', max: 5e7 },
  { label: '5000 万–1 亿', max: 1e8 },
  { label: '1 亿–5 亿', max: 5e8 },
  { label: '5 亿以上', max: Infinity },
];

const pad = (n) => String(n).padStart(2, '0');
const todayDate = new Date();
const today = `${todayDate.getFullYear()}-${pad(todayDate.getMonth() + 1)}-${pad(todayDate.getDate())}`;
const trim = (value) => Number(Number(value).toFixed(4));

// ---- 扫描设置 ----
const config = reactive(createDefaultHengpanConfig(DEFAULT_RULE));
// 这个参数在这一组的箱体模式下是否生效；旧版保存的规则没有 box_type，按固定箱高处理
const fieldApplies = (rule, key) => !RULE_FIELDS[key].only || RULE_FIELDS[key].only === (rule.box_type || 'fixed');
// 规则表只显示当前用得到的列：全是固定箱高就不出现「振幅倍数」，
// 全是振幅倍数就不出现「十字星振幅上限」和「箱体高度」；两种模式混用时才都显示
const visibleFields = computed(() => {
  const modes = new Set(config.rules.map(rule => rule.box_type || 'fixed'));
  return Object.entries(RULE_FIELDS).filter(([, field]) => !field.only || modes.has(field.only));
});
// 旧版保存的规则组缺新字段，补上默认值
const normalizeRule = (rule) => ({ ...DEFAULT_RULE, ...rule });
const sameRule = (a, b) => a.box_type === b.box_type &&
  Object.keys(RULE_FIELDS).every(key => !fieldApplies(a, key) || a[key] === b[key]);
const isDefaultRules = computed(() => config.rules.length === 1 && sameRule(config.rules[0], DEFAULT_RULE));
const savedRuleGroups = ref([]);
const selectedRuleGroupId = ref('');

function addRule () {
  if (config.rules.length < MAX_RULES) config.rules.push({ ...config.rules[config.rules.length - 1] });
}
function removeRule (index) {
  if (config.rules.length > 1) config.rules.splice(index, 1);
}
function resetRules () {
  config.rules = [{ ...DEFAULT_RULE }];
}
function usePreset () {
  config.rules = PRESET_RULES.map(normalizeRule);
}

function saveCurrentRuleGroup () {
  formError.value = validate();
  if (formError.value) return;
  const { saved, groups } = saveRuleGroup(window.localStorage, savedRuleGroups.value, config.rules);
  savedRuleGroups.value = groups;
  selectedRuleGroupId.value = saved.id;
  notify(`已保存为${saved.name}`);
}

function applySavedRuleGroup () {
  const group = savedRuleGroups.value.find(item => item.id === selectedRuleGroupId.value);
  if (!group) return;
  config.rules = group.rules.map(normalizeRule);
  formError.value = '';
}

function removeSavedRuleGroup () {
  const group = savedRuleGroups.value.find(item => item.id === selectedRuleGroupId.value);
  if (!group || !window.confirm(`确定删除${group.name}吗？`)) return;
  savedRuleGroups.value = deleteRuleGroup(
    window.localStorage,
    savedRuleGroups.value,
    selectedRuleGroupId.value,
  );
  selectedRuleGroupId.value = '';
  notify(`已删除${group.name}`);
}

const boardLabel = (key) => BOARDS.find(b => b.key === key)?.label || key;
const scopeLabel = (markets) => (markets && markets.length ? markets.map(boardLabel).join('、') : '全部 A 股');
// 板块筛选 chip：点一下加入 / 移出
function toggleMarket (key) {
  config.markets = config.markets.includes(key)
    ? config.markets.filter((item) => item !== key)
    : [...config.markets, key];
}

const marketsHint = computed(() => config.markets.length
  ? `将扫描：${scopeLabel(config.markets)}`
  : '未选择板块，将扫描全部 A 股（约 5200 只，需要 10 多分钟）；数据源 Baostock 没有北交所数据');
// 规则标签：固定箱高用「箱高% / 回验根数」，振幅模式用「振幅 ×倍数 / 回验根数」，参数表和结果区共用
const formatRule = (boxType, boxPct, multiple, lookback) => (boxType === 'amplitude'
  ? `振幅 ×${trim(multiple)} / ${lookback} 根`
  : `${trim(boxPct)}% / ${lookback} 根`);
const frequencyLabel = computed(() =>
  FREQUENCY_OPTIONS.find(option => option.value === config.frequency)?.label || '60 分钟 K 线');
const frequencyHint = computed(() => config.frequency === '60'
  ? '默认使用数据源返回的最新一根 60 分钟 K 线（盘中可能尚未完成）。'
  : '使用交易日 K 线，沿用日线扫描口径。');
const averageWindowLabel = computed(() =>
  config.frequency === '60' ? `${activeLookback.value} 根 K 线平均` : `${activeLookback.value} 日均`);
const summaryText = computed(() => [
  `${config.rules.length} 组规则：${config.rules.map(r => formatRule(r.box_type, r.box_pct, r.amp_multiple, r.lookback)).join('，')}`,
  frequencyLabel.value,
  config.scan_date ? `扫描日 ${config.scan_date}` : '最新交易日',
  scopeLabel(config.markets),
].join(' · '));

const formError = ref('');

function validate () {
  for (const [index, rule] of config.rules.entries()) {
    for (const [key, field] of Object.entries(RULE_FIELDS)) {
      if (!fieldApplies(rule, key)) continue;
      const value = rule[key];
      if (typeof value !== 'number' || !Number.isFinite(value)) return `第 ${index + 1} 组：请填写「${field.label}」`;
      if (value < field.min || value > field.max) {
        return `第 ${index + 1} 组：「${field.label}」应在 ${field.min} 到 ${field.max} ${field.unit}之间`;
      }
    }
    if (!Number.isInteger(rule.lookback) || !Number.isInteger(rule.max_breach)) {
      return `第 ${index + 1} 组：回验根数和允许越界根数应为整数`;
    }
    if (rule.max_breach >= rule.lookback) return `第 ${index + 1} 组：允许越界根数应小于回验根数`;
    const twin = config.rules.findIndex(other => sameRule(other, rule));
    if (twin !== index) return `第 ${index + 1} 组与第 ${twin + 1} 组完全相同，请删掉重复的一组`;
  }
  if (config.scan_date && config.scan_date > today) return '扫描日不能晚于今天';
  return '';
}

function buildPayload () {
  return {
    rules: config.rules.map(rule => {
      // 这一组模式用不到的参数填默认值：输入框可能是空的，后端判重也只看用到的参数
      const value = (key) => (fieldApplies(rule, key) ? rule[key] : DEFAULT_RULE[key]);
      return {
        box_type: rule.box_type,
        doji_amplitude: trim(value('doji_pct') / 100),
        box_height: trim(value('box_pct') / 100),
        amp_multiple: trim(value('amp_multiple')),
        // 振幅上限留空表示不限，不传这个字段
        max_amplitude: rule.box_type === 'amplitude' && Number(rule.max_amp_pct) > 0
          ? trim(rule.max_amp_pct / 100) : null,
        lookback: rule.lookback,
        max_breach: rule.max_breach,
      };
    }),
    frequency: config.frequency,
    scan_date: config.scan_date || null,
    markets: config.markets,
  };
}

// ---- 扫描任务 ----
const scan = reactive({
  status: 'idle', progress: 0, message: '', error: '', startedAt: 0, finishedAt: 0,
  scanned: 0, total: 0, scanDate: '', frequency: '60', stats: null, rules: [], params: null,
});
const scanFrequencyLabel = computed(() => scan.frequency === '60' ? '60 分钟 K 线' : '日线');
const isScanning = computed(() => scan.status === 'running');
const results = ref([]);
const activeRuleId = ref('1');
const currentTaskId = ref(null);
const resultsRef = ref(null);
const now = ref(Date.now());
let pollTimer = null;
let clockTimer = null;
let streamCursor = 0; // 边扫边出：记录已拉取到的结果数
const cancelRequested = ref(false);
const histories = ref([]);
const selectedHistoryId = ref('');
const historyLoading = ref(false);

const ruleLabel = (rule) =>
  formatRule(rule.params.box_type, rule.params.box_height * 100, rule.params.amp_multiple, rule.params.lookback);
const ruleById = (id) => scan.rules.find(rule => rule.id === id);
// 多组规则时始终给切换按钮：某组 0 只也要能切过去看其他组的统计
const showRuleTabs = computed(() => scan.rules.length > 1 && scan.status !== 'failed');
const activeRule = computed(() => ruleById(activeRuleId.value) || scan.rules[0]);
const isAmplitudeRule = computed(() => activeRule.value?.params.box_type === 'amplitude');
const activeLookback = computed(() => activeRule.value?.params.lookback ?? DEFAULT_RULE.lookback);
const activeRuleDetail = computed(() => {
  const params = activeRule.value?.params;
  if (!params) return '';
  if (params.box_type === 'amplitude') {
    return `末端 K 线上下各延伸 ${trim(params.amp_multiple)} 倍振幅 · ` +
      `回验 ${params.lookback} 根 · 容错 ${params.max_breach} 根`;
  }
  return `十字星 ≤ ${trim(params.doji_amplitude * 100)}% · 箱高 ${trim(params.box_height * 100)}% · ` +
    `回验 ${params.lookback} 根 · 容错 ${params.max_breach} 根`;
});

// 这只股票在某一组规则下算不算入选。实体口径下 matches 里的都算，整体口径还要看 passed_full
const qualifies = (stock, ruleId, which) => {
  const match = stock.matches[ruleId];
  return !!match && (which === 'body' || match.passed_full);
};
// 这只股票在当前口径下命中的全部规则编号，按规则填写的先后顺序
const matchedRules = (stock, which) =>
  scan.rules.filter(rule => qualifies(stock, rule.id, which)).map(rule => rule.id);
// 「只看本组新增」把每只股票只归给第一个命中它的组：放宽的组本来就含着严格组选出的股票，
// 按先后顺序归属之后各组互不重复，加起来正好是全部命中数
const belongsHere = (stock, ruleId, which) => matchedRules(stock, which)[0] === ruleId;

// 每组规则的入选数。默认取后端统计：结果被上限截断时这个数字仍然完整；
// 「只看本组新增」下改成按已返回的结果现算，因为后端统计不区分股票归属哪一组
function ruleCount (ruleId, which = basis.value, exclusive = exclusiveOnly.value) {
  if (exclusive) {
    return results.value.filter(stock => belongsHere(stock, ruleId, which)).length;
  }
  const stat = scan.stats?.rules?.[ruleId];
  if (stat) return which === 'body' ? stat.passed_body : stat.passed_full;
  return results.value.filter(stock => qualifies(stock, ruleId, which)).length;
}

function appendResults (items) {
  if (!Array.isArray(items) || !items.length) return;
  const existing = new Set(results.value.map(stock => stock.code));
  const fresh = items.filter(stock => stock && stock.code && !existing.has(stock.code));
  if (fresh.length) results.value.push(...fresh);
}

function stopTimers () {
  clearInterval(pollTimer);
  clearInterval(clockTimer);
  pollTimer = clockTimer = null;
}
onUnmounted(stopTimers);

function finish (status, fields = {}) {
  stopTimers();
  streamCursor = 0;
  cancelRequested.value = false;
  Object.assign(scan, { status, finishedAt: Date.now(), ...fields });
  loadHistories();
}

async function startScan () {
  if (isScanning.value) return;
  formError.value = validate();
  if (formError.value) return;

  const payload = buildPayload();
  selectedHistoryId.value = '';
  cancelRequested.value = false;
  Object.assign(scan, {
    status: 'running', progress: 0, message: '正在提交扫描任务…', error: '', startedAt: Date.now(), finishedAt: 0,
    scanned: 0, total: 0, scanDate: '', frequency: payload.frequency, stats: null, rules: [], params: payload,
  });
  now.value = Date.now();
  streamCursor = 0;
  clockTimer = setInterval(() => { now.value = Date.now(); }, 1000);
  results.value = [];
  activeRuleId.value = '1';
  resetFilters();

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  nextTick(() => resultsRef.value?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' }));

  try {
    const { data } = await axios.post(`${API}/start`, payload);
    currentTaskId.value = data.task_id;
    scan.message = data.message;
    pollTimer = setInterval(() => poll(data.task_id), 2000);
  } catch (e) {
    finish('failed', { message: `扫描任务提交失败：${e.message}` });
  }
}

async function poll (taskId) {
  try {
    const { data } = await axios.get(`${API}/status/${taskId}?since=${streamCursor}`);
    scan.progress = data.progress;
    scan.message = data.message;
    scan.scanned = data.scanned || 0;
    scan.total = data.total || 0;
    if (typeof data.cancel_requested === 'boolean') cancelRequested.value = data.cancel_requested;
    if (data.frequency === '60' || data.frequency === 'd') scan.frequency = data.frequency;
    if (data.scan_date) scan.scanDate = data.scan_date;
    if (data.stats) scan.stats = data.stats;
    if (data.rules) scan.rules = data.rules;

    // 边扫边出：追加新结果
    appendResults(data.new_results);
    if (typeof data.cursor === 'number') streamCursor = data.cursor;

    if (data.status === 'completed' || data.status === 'cancelled') {
      // 最后一次拉完整结果，确保没遗漏
      results.value = [];
      appendResults(data.result || []);
      finish(data.status);
    } else if (data.status === 'failed') {
      finish('failed', { message: data.message, error: data.error || '' });
    }
  } catch (e) {
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
    await axios.post(`${API}/cancel/${currentTaskId.value}`);
    scan.message = '正在停止扫描…';
  } catch (e) {
    cancelRequested.value = false;
    notify(`停止扫描失败：${e.message || '请稍后重试'}`, 'error');
    console.error('停止扫描失败:', e);
  }
}

// ---- 历史结果 ----
function toTimestampMs (value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return 0;
  return timestamp < 1e12 ? timestamp * 1000 : timestamp;
}

function formatHistoryLabel (item) {
  const rules = (item.rules || []).map(rule =>
    `${ruleLabel(rule)} ${item.passed_full_by_rule?.[rule.id] ?? 0}`).join('，');
  const createdAt = toTimestampMs(item.created_at);
  const when = createdAt
    ? new Date(createdAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '';
  const status = item.status === 'cancelled' ? ' 已停止' : '';
  const frequency = (item.frequency ?? item.params?.frequency) === '60' ? '60 分钟' : '日线';
  return `${item.scan_date || '—'} · ${frequency} · ${scopeLabel(item.markets)} · ${rules || '—'} · ${when}${status}`;
}

async function loadHistory () {
  if (!selectedHistoryId.value) return;
  historyLoading.value = true;
  try {
    const { data } = await axios.get(`${API}/history/${selectedHistoryId.value}`);
    applySnapshot(data, '已加载历史扫描');
  } catch (e) {
    notify(`加载历史结果失败：${e.message}`, 'error');
  } finally {
    historyLoading.value = false;
  }
}

// 把一份快照（历史详情或导入的文件，格式相同）原样展示到本页
function applySnapshot (data, label) {
  const rules = data.rules || [];
  // 表单恢复成这次扫描用的规则，方便在此基础上调整后重扫
  if (rules.length) {
    config.rules = rules.map(rule => ({
      box_type: rule.params.box_type || 'fixed',
      doji_pct: trim(rule.params.doji_amplitude * 100),
      box_pct: trim(rule.params.box_height * 100),
      max_amp_pct: rule.params.max_amplitude ? trim(rule.params.max_amplitude * 100) : null,
      amp_multiple: rule.params.amp_multiple ?? DEFAULT_RULE.amp_multiple,
      lookback: rule.params.lookback,
      max_breach: rule.params.max_breach,
    }));
  }
  // New snapshots persist frequency at the top level. Old snapshots do not
  // have it and intentionally retain the historical daily default.
  config.frequency = (data.frequency ?? data.params?.frequency) === '60' ? '60' : 'd';
  config.scan_date = data.params?.scan_date || '';
  config.markets = data.params?.markets || [];
  results.value = [];
  appendResults(data.results || []);
  Object.assign(scan, {
    status: data.status === 'cancelled' ? 'cancelled' : 'completed',
    progress: 100,
    message: `${label}：${results.value.length} 只股票`,
    error: '',
    scanned: Number(data.scanned || 0),
    total: Number(data.total || 0),
    scanDate: data.scan_date || '',
    frequency: data.frequency ?? data.params?.frequency ?? 'd',
    stats: data.stats || null,
    rules,
    params: data.params || null,
    startedAt: toTimestampMs(data.created_at),
    finishedAt: toTimestampMs(data.completed_at ?? data.saved_at) || Date.now(),
  });
  activeRuleId.value = rules[0]?.id || '1';
  resetFilters();
}

// ---- 导出 / 导入 ----
const importInput = ref(null);
const canExport = computed(() => ['completed', 'cancelled'].includes(scan.status) && scan.rules.length > 0);

// 导出的文件和后端历史快照同一格式，导入时直接复用 applySnapshot
function exportResults () {
  const snapshot = {
    status: scan.status,
    message: scan.message,
    created_at: scan.startedAt / 1000,
    completed_at: scan.finishedAt / 1000,
    scan_date: scan.scanDate,
    frequency: scan.frequency,
    params: scan.params,
    rules: scan.rules,
    stats: scan.stats,
    scanned: scan.scanned,
    total: scan.total,
    found: results.value.length,
    results: results.value,
  };
  const frequency = scan.frequency === '60' ? '60分钟' : '日线';
  const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `横盘选股_${scan.scanDate || '未知日期'}_${frequency}_${results.value.length}只.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function importResults (event) {
  const file = event.target.files?.[0];
  event.target.value = ''; // 允许重复选同一个文件
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data?.rules) || !data.rules.length || !Array.isArray(data.results)) {
      throw new Error('不是横盘选股导出的结果文件');
    }
    selectedHistoryId.value = '';
    applySnapshot(data, `已导入 ${file.name}`);
  } catch (e) {
    notify(`导入失败：${e.message}`, 'error');
  }
}

async function loadHistories () {
  try {
    const { data } = await axios.get(`${API}/history`);
    histories.value = data.histories || [];
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

// ---- 统计 ----
const showStats = computed(() => ['running', 'completed', 'cancelled'].includes(scan.status) && !!scan.stats);
const statTiles = computed(() => {
  const { skipped } = scan.stats || {};
  const stat = scan.stats?.rules?.[activeRuleId.value];
  const ruleNote = activeRule.value ? ruleLabel(activeRule.value) : '';
  // 统计格始终给这一组的完整入选数；开了「只看本组新增」时补一句新增多少，避免和标签上的数字对不上
  const note = (which) => exclusiveOnly.value
    ? `${ruleNote} · 本组新增 ${ruleCount(activeRuleId.value, which, true)}`
    : ruleNote;
  return [
    { label: '扫描日', value: scan.scanDate || '—' },
    { label: '数据周期', value: scanFrequencyLabel.value },
    { label: '已分析', value: fmtCount(scan.scanned), note: scan.total ? `共 ${fmtCount(scan.total)} 只` : '' },
    { label: '整体口径入选', value: fmtCount(ruleCount(activeRuleId.value, 'full', false)), note: note('full') },
    { label: '实体口径入选', value: fmtCount(ruleCount(activeRuleId.value, 'body', false)), note: note('body') },
    {
      label: '跳过',
      // suspended 是后加的，旧的扫描历史里没有这一项，按 0 算
      value: skipped ? fmtCount(skipped.stale + skipped.insufficient + skipped.failed + (skipped.suspended || 0)) : '—',
      note: skipped ? `当日无交易 ${skipped.stale} · 数据不足 ${skipped.insufficient} · 窗口内停牌 ${skipped.suspended || 0} · 取数失败 ${skipped.failed}` : '',
    },
    {
      label: '十字星分界附近',
      value: stat && !isAmplitudeRule.value ? fmtCount(stat.near) : '—',
      note: isAmplitudeRule.value ? '振幅模式不区分十字星' : (stat ? `换一种模式能入选 ${stat.rescued} 只` : ''),
    },
  ];
});
// 大半股票在扫描日没有所选周期数据，多半是数据源还没更新完
const staleWarning = computed(() =>
  !!scan.stats && scan.scanned >= 50 && scan.stats.skipped.stale > scan.scanned / 2);

// ---- 结果筛选与分页 ----
const basis = ref('full');
const exclusiveOnly = ref(false); // 每只股票只归第一个命中它的组，让各组互不重复
const modeFilter = ref('');
const keyword = ref('');
const industry = ref('');
const hideSt = ref(false);
const sortBy = ref('default');
const pageSize = ref(12);
const page = ref(1);

function clearFilters () {
  modeFilter.value = '';
  keyword.value = '';
  industry.value = '';
  hideSt.value = false;
  page.value = 1;
}

function resetFilters () {
  clearFilters();
  basis.value = 'full';
  exclusiveOnly.value = false;
  sortBy.value = 'default';
}

// 上轨下轨按规则各不相同，这里按当前规则现算，后端不必为每组重复下发
function markLinesFor (match) {
  return [
    { type: 'horizontal', value: match.upper, text: '上轨', color: '#ec0000' },
    { type: 'horizontal', value: match.lower, text: '下轨', color: '#10b981' },
    { date: match.lookback_start, text: '回验起点', color: '#3b82f6' },
  ];
}

// 当前规则下命中的股票，每只带上这一组的判定结果和标记线；
// 「只看本组独有」会滤掉同时命中别组的，让各组之间互不重复
const basisResults = computed(() => {
  const ruleId = activeRuleId.value;
  const which = basis.value;
  return results.value.flatMap(stock => {
    if (!qualifies(stock, ruleId, which)) return [];
    const others = matchedRules(stock, which).filter(id => id !== ruleId);
    if (exclusiveOnly.value && !belongsHere(stock, ruleId, which)) return [];
    return [{
      ...stock,
      match: stock.matches[ruleId],
      markLines: markLinesFor(stock.matches[ruleId]),
      otherRules: others.map(id => { const rule = ruleById(id); return rule ? ruleLabel(rule) : id; }),
    }];
  });
});
const modeCount = (mode) => (mode ? basisResults.value.filter(s => s.match.mode === mode).length : basisResults.value.length);

const amountBuckets = computed(() => AMOUNT_BUCKETS.map((bucket, i) => {
  const min = i ? AMOUNT_BUCKETS[i - 1].max : 0;
  return {
    label: bucket.label,
    count: basisResults.value.filter(s => s.match.avg_amount != null &&
      s.match.avg_amount >= min && s.match.avg_amount < bucket.max).length,
  };
}));

const industryOptions = computed(() => {
  const counter = {};
  basisResults.value.forEach(s => { const name = s.industry || '未知行业'; counter[name] = (counter[name] || 0) + 1; });
  return Object.entries(counter).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
});

const filteredResults = computed(() => {
  const kw = keyword.value.toLowerCase();
  return basisResults.value
    .filter(s =>
      (isAmplitudeRule.value || !modeFilter.value || s.match.mode === modeFilter.value) &&
      (!hideSt.value || !s.is_st) &&
      (!industry.value || (s.industry || '未知行业') === industry.value) &&
      (!kw || s.code.toLowerCase().includes(kw) || s.name.toLowerCase().includes(kw)))
    .sort(SORTS[sortBy.value].compare);
});
const totalPages = computed(() => Math.max(1, Math.ceil(filteredResults.value.length / pageSize.value)));
const pagedResults = computed(() =>
  filteredResults.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value));
watch([basis, exclusiveOnly, modeFilter, keyword, industry, hideSt, sortBy, pageSize, activeRuleId],
  () => { page.value = 1; });

function goPage (target) {
  page.value = Math.min(Math.max(1, target), totalPages.value);
  resultsRef.value?.scrollIntoView({ block: 'start' });
}

// ---- 格式化 ----
const fmtCount = (n) => Number(n || 0).toLocaleString('zh-CN');
const fmtPrice = (v) => (typeof v === 'number' ? v.toFixed(2) : '—');
const fmtPct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : '—');
const fmtTurn = (v) => (typeof v === 'number' ? `${v.toFixed(2)}%` : '—');
const fmtAmount = (v) => {
  if (typeof v !== 'number') return '—';
  return v >= 1e8 ? `${(v / 1e8).toFixed(2)} 亿` : `${Math.round(v / 1e4).toLocaleString('zh-CN')} 万`;
};
// 振幅模式的箱高随末端 K 线变化，按和「实际震荡」相同的口径（除以最低价）现算
const boxHeight = (match) => (match.lower > 0 ? (match.upper - match.lower) / match.lower : null);

// ---- 大图与提示 ----
const showFullChart = ref(false);
const chartStock = ref(null);
const chartTitle = computed(() => {
  const stock = chartStock.value;
  if (!stock) return '';
  const rule = activeRule.value ? ` · ${ruleLabel(activeRule.value)}` : '';
  return `${stock.name}（${stock.code}）· ${MODES[stock.match.mode].label}${rule}`;
});
const chartMarkLines = computed(() => chartStock.value?.markLines || []);

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

onMounted(() => {
  savedRuleGroups.value = loadRuleGroups(window.localStorage);
  loadHistories();
});
</script>

<style scoped>
/* ---------- Hero ---------- */
.hero {
  position: relative;
  display: flex;
  align-items: center;
  gap: 24px;
  overflow: hidden;
  padding: 28px 32px;
  border-radius: 28px;
  background:
    radial-gradient(120% 140% at 100% 0%, color-mix(in srgb, var(--md-tertiary-container) 90%, transparent) 0%, transparent 60%),
    linear-gradient(135deg, var(--md-primary-container), color-mix(in srgb, var(--md-secondary-container) 80%, var(--md-primary-container)));
  color: var(--md-on-primary-container);
}
.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
  background: color-mix(in srgb, var(--md-on-primary-container) 10%, transparent);
}
.hero-art {
  display: none;
  width: 240px;
  flex-shrink: 0;
  overflow: visible;
}
@media (min-width: 768px) { .hero-art { display: block; } }
.hero-box {
  fill: color-mix(in srgb, var(--md-on-primary-container) 6%, transparent);
  stroke: color-mix(in srgb, var(--md-on-primary-container) 45%, transparent);
  stroke-width: 1.5;
  stroke-dasharray: 5 5;
  animation: hero-dash 12s linear infinite;
}
.hero-candle {
  transform-box: fill-box;
  transform-origin: center;
  animation: hero-candle 700ms var(--md-ease-spring) both;
  animation-delay: calc(200ms + var(--i) * 60ms);
}
.hero-candle line { stroke: color-mix(in srgb, var(--md-on-primary-container) 55%, transparent); stroke-width: 1.5; }
.hero-candle rect { fill: color-mix(in srgb, var(--md-on-primary-container) 70%, transparent); }
.hero-candle rect.is-last { fill: var(--md-primary); animation: hero-pulse 2.4s var(--md-ease-standard) infinite 1.4s; }
.hero-break {
  fill: none;
  stroke: var(--md-primary);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-dasharray: 40;
  stroke-dashoffset: 40;
  animation: hero-draw 800ms var(--md-ease-emphasized-decelerate) forwards 1.1s;
}
@keyframes hero-candle { from { opacity: 0; transform: scaleY(0.2); } to { opacity: 1; transform: none; } }
@keyframes hero-draw { to { stroke-dashoffset: 0; } }
@keyframes hero-dash { to { stroke-dashoffset: -100; } }
@keyframes hero-pulse { 50% { opacity: 0.45; } }

/* ---------- 区块标题 ---------- */
.section-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  line-height: 24px;
  font-weight: 500;
}
.section-icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}

/* ---------- 分段切换（M3 segmented button） ---------- */
.seg {
  display: inline-flex;
  flex-wrap: wrap;
  overflow: hidden;
  border-radius: 9999px;
  border: 1px solid var(--md-outline);
}
.seg-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 36px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--md-on-surface);
  isolation: isolate;
  overflow: hidden;
  transition: background-color var(--md-duration-short) var(--md-ease-standard);
}
.seg-btn + .seg-btn { border-left: 1px solid var(--md-outline); }
.seg-btn:hover { background: color-mix(in srgb, var(--md-on-surface) 8%, transparent); }
.seg-btn.is-active { background: var(--md-secondary-container); color: var(--md-on-secondary-container); }

/* ---------- 次要按钮（M3 outlined） ---------- */
.btn-quiet {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  white-space: nowrap;
  border-radius: 9999px;
  border: 1px solid var(--md-outline-variant);
  color: var(--md-primary);
  font-size: 13px;
  font-weight: 500;
  isolation: isolate;
  overflow: hidden;
  transition: background-color var(--md-duration-short) var(--md-ease-standard);
}
.btn-quiet:hover:not(:disabled) { background: color-mix(in srgb, var(--md-primary) 8%, transparent); }
.btn-quiet:disabled { cursor: not-allowed; opacity: 0.45; }

/* ---------- 图标按钮 ---------- */
.help-btn {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 9999px;
  color: var(--md-on-surface-variant);
  transition: background-color var(--md-duration-short) var(--md-ease-standard);
}
.help-btn:hover { background: color-mix(in srgb, var(--md-on-surface) 8%, transparent); color: var(--md-on-surface); }

/* ---------- 小标签 ---------- */
.tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.03em;
  background: var(--md-surface-container-highest);
  color: var(--md-on-surface-variant);
}
.tag-primary { background: var(--md-primary-container); color: var(--md-on-primary-container); }
.tag-danger { background: var(--md-error-container); color: var(--md-on-error-container); }

/* ---------- 选择框：与 .input 同一套外观 ---------- */
.select {
  height: 40px;
  padding: 0 34px 0 12px;
  border-radius: 12px;
  border: 1px solid var(--md-outline-variant);
  background: var(--md-surface-container-lowest) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 24 24' fill='%23777'%3E%3Cpath d='M7 10l5 5 5-5z'/%3E%3C/svg%3E") no-repeat right 8px center;
  color: var(--md-on-surface);
  appearance: none;
  transition: border-color var(--md-duration-short) var(--md-ease-standard);
}
.select:hover { border-color: var(--md-outline); }
.select:focus { outline: none; border-color: var(--md-primary); box-shadow: inset 0 0 0 1px var(--md-primary); }

/* ---------- 统计格与结果卡 ---------- */
.stat-tile {
  border-radius: 18px;
  padding: 12px 16px;
  background: var(--md-surface-container);
}
.result-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 24px;
  background: var(--md-surface);
  border: 1px solid var(--md-outline-variant);
}
.empty-icon {
  display: inline-grid;
  place-items: center;
  width: 80px;
  height: 80px;
  border-radius: 28px;
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}

.seg-btn:focus-visible,
.btn-quiet:focus-visible,
.help-btn:focus-visible,
.select:focus-visible {
  outline: 2px solid var(--md-primary);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .hero-candle, .hero-break, .hero-box, .hero-candle rect.is-last { animation: none; opacity: 1; stroke-dashoffset: 0; }
}
</style>
