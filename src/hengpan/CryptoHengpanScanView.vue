<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <!-- 完整K线图弹窗 -->
    <FullKlineChart v-if="showFullChart" :kline-url="chartSymbol?.kline_url" v-model:visible="showFullChart" :title="chartTitle"
      :klineData="chartSymbol ? chartSymbol.kline_data : []" :markLines="chartMarkLines" :isDarkMode="isDarkMode" :ma-period="chartSymbol?.match?.ma_period" :bollinger="chartSymbol?.match" />

    <!-- Hero：一句话说清楚这页干什么，右侧是会动的箱体示意 -->
    <section class="hero rise-in" aria-label="页面说明">
      <div class="relative z-10 min-w-0 flex-1">
        <p class="flex items-center gap-2 text-label-l opacity-80"><MIcon name="crop_free" :size="18" />末端锚定横盘箱体 · 永续合约</p>
        <h2 class="mt-2 text-headline-m">找出正在横盘蓄势的永续合约</h2>
        <p class="mt-2 max-w-2xl text-body-m opacity-85">
          {{ heroDescription }}
        </p>
        <div class="mt-4 flex flex-wrap gap-2">
          <span class="hero-chip"><MIcon name="rule" :size="16" />{{ config.rules.length }} 组规则</span>
          <span class="hero-chip"><MIcon name="schedule" :size="16" />{{ FREQUENCY_LABEL }}</span>
          <span class="hero-chip"><MIcon name="category" :size="16" />{{ scopeLabel(config.categories) }}</span>
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
            <button type="button" class="btn btn-text btn-sm" @click="usePreset"><MIcon name="auto_awesome" :size="18" />{{ ['ma_flat', 'boll_box'].includes(activeBoxType) ? '试验组合' : '用推荐组合' }}</button>
            <button v-if="!isDefaultRules" type="button" class="btn btn-text btn-sm"
              @click="resetRules"><MIcon name="restart_alt" :size="18" />恢复默认</button>
          </div>
        </div>
        <p class="mt-1 text-xs text-muted-foreground">
          最多 {{ MAX_RULES }} 组，一次扫描全部算完。判定口径与横盘-A 完全相同，规则组两页通用。
        </p>

        <div class="mt-4 max-w-sm">
          <label for="cu-box-mode" class="mb-1 block text-sm font-medium">横盘模式</label>
          <select id="cu-box-mode" class="select w-full" :value="activeBoxType" @change="changeBoxType">
            <option v-for="(item, key) in BOX_MODES" :key="key" :value="key">{{ item.label }}</option>
          </select>
          <p class="mt-1.5 text-xs text-muted-foreground">{{ BOX_MODES[activeBoxType].description }}</p>
        </div>

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

        <RuleEditorTable :fields="activeRuleFields" :rules="config.rules" :max-rules="MAX_RULES"
          @add="addRule" @remove="removeRule" />

        <details class="mt-5 text-sm">
          <summary class="cursor-pointer text-muted-foreground hover:text-foreground">规则怎么算</summary>
          <ol v-if="BOX_MODES[activeBoxType].help" class="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
            <li v-for="line in BOX_MODES[activeBoxType].help" :key="line">{{ line }}</li>
          </ol>
          <ol v-else-if="activeBoxType === 'fixed'" class="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>固定箱高：末端 K 线振幅 =（最高 − 最低）÷ 收盘。不超过「十字星振幅上限」算十字星，否则算普通 K 线。</li>
            <li>十字星认定在箱顶：中点就是上轨，下轨 = 上轨 ×（1 − 箱体高度）。</li>
            <li>普通 K 线认定在箱体中间：中点就是中轨，上下各延伸半个箱高。</li>
            <li>末端之前的「回验根数」根 K 线里，越出箱体的不超过「允许越界」根才入选。末端位置认错时箱体会放偏，套不住历史 K 线，自动淘汰。</li>
            <li>整体口径把影线算进去，是默认标准；实体口径只看开盘价和收盘价，更宽松。两种口径一次算完，结果里可以切换。</li>
          </ol>
          <ol v-else-if="activeBoxType === 'amplitude'" class="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>以末端 K 线最高价、最低价为基准，上下各延伸指定倍数的末端振幅。</li>
            <li>末端振幅超过可选上限时直接淘汰，避免大 K 线把箱体撑得过宽。</li>
            <li>回验区间允许少量整体或实体越界，结果区可以切换两种口径。</li>
          </ol>
          <ol v-else class="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>用最近 K 线的实体中心价（开盘价与收盘价的平均值）寻找覆盖最多数据的主体箱体。</li>
            <li>开盘价或收盘价越轨记为一根实体刺；仅影线越轨只展示，不影响入选。</li>
            <li>实体刺总数不能超过允许值，连续实体刺不能超过连续上限。</li>
            <li>首尾各三分之一的实体中心明显换挡时，视为两个箱体并淘汰。</li>
          </ol>
        </details>
      </div>

      <!-- 扫描范围 -->
      <div class="p-5 sm:p-6">
        <h2 class="section-title"><span class="section-icon"><MIcon name="travel_explore" :size="20" /></span>扫描范围</h2>
        <div class="mt-4 grid gap-x-8 gap-y-5 md:grid-cols-[18rem_minmax(0,1fr)]">
          <div>
            <label for="cu-scan-date" class="mb-1 block text-sm font-medium">扫描日</label>
            <div class="flex gap-2">
              <input id="cu-scan-date" v-model="config.scan_date" class="input" type="date" :max="today">
              <button v-if="config.scan_date" type="button" class="btn-quiet h-10 px-3" @click="config.scan_date = ''">清空</button>
            </div>
            <p class="mt-1.5 text-xs text-muted-foreground">
              {{ config.scan_date ? '取这一天（北京时间）最后一根 1 小时线作为末端' : '留空取本地行情最新一天的最后一根 1 小时线' }}
            </p>
          </div>
          <div>
            <label for="cu-min-volume" class="mb-1 block text-sm font-medium">24 小时成交额门槛</label>
            <div class="flex items-center gap-2">
              <input id="cu-min-volume" v-model.number="config.min_quote_wan" class="input w-32" type="number"
                min="0" step="100">
              <span class="whitespace-nowrap text-sm text-muted-foreground">万 USDT</span>
              <button v-if="config.min_quote_wan" type="button" class="btn-quiet h-10 px-3"
                @click="config.min_quote_wan = 0">不限</button>
            </div>
            <p class="mt-1.5 text-xs text-muted-foreground">
              {{ config.min_quote_wan ? `只扫 24 小时成交额不低于 ${fmtCount(config.min_quote_wan)} 万 USDT 的交易对` : '不限成交额；流动性很差的交易对本来就不怎么动，容易被当成横盘' }}
            </p>
          </div>
          <div class="md:col-span-2">
            <span id="cu-categories" class="mb-1 block text-sm font-medium">类别</span>
            <div class="mt-2 flex flex-wrap gap-2" role="group" aria-labelledby="cu-categories">
              <button v-for="item in CATEGORIES" :key="item.key" type="button" class="chip"
                :class="config.categories.includes(item.key) && 'is-selected'"
                :aria-pressed="config.categories.includes(item.key)" @click="toggleCategory(item.key)">
                <MIcon v-if="config.categories.includes(item.key)" name="check" />{{ item.label }}
              </button>
            </div>
            <p class="mt-1.5 text-xs text-muted-foreground">{{ categoriesHint }}</p>
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
      <HistorySaveStatus :state="historyPersistence.state" @retry="historyPersistence.retry" />
      <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-5 py-4 sm:px-6">
        <div class="flex items-center gap-2">
          <h2 class="section-title"><span class="section-icon"><MIcon name="insights" :size="20" /></span>扫描结果</h2>
          <span v-if="scan.status !== 'idle'" class="tag tag-primary">{{ FREQUENCY_LABEL }}</span>
        </div>
        <p v-if="scan.finishedAt && scan.status !== 'running'" class="text-xs text-muted-foreground">
          用时 {{ formatDuration(scan.finishedAt - scan.startedAt) }}
        </p>
        <div class="flex items-center gap-2">
          <HistoryLink kind="hengpan_u" />
          <label class="text-xs text-muted-foreground" for="cu-history">历史结果</label>
          <select id="cu-history" v-model="selectedHistoryId" class="select h-8 max-w-[28rem] text-xs"
            :disabled="isScanning || historyLoading" @change="loadHistory">
            <option value="">选择历史扫描…</option>
            <option v-for="item in histories" :key="item.history_id" :value="item.history_id">
              {{ formatHistoryLabel(item) }}
            </option>
          </select>
          <button type="button" class="help-btn" :disabled="!selectedHistoryId || isScanning || historyLoading"
            title="删除选中的历史扫描" aria-label="删除选中的历史扫描" @click="deleteSelectedHistory">
            <MIcon name="delete" :size="18" />
          </button>
          <details class="relative">
            <summary class="btn-quiet flex h-8 cursor-pointer list-none items-center gap-1 px-2 text-xs"
              :class="(isScanning || historyLoading) && 'pointer-events-none opacity-50'"
              :aria-disabled="isScanning || historyLoading">
              <MIcon name="delete_sweep" :size="17" />清理旧记录
            </summary>
            <div class="absolute right-0 z-20 mt-2 w-64 rounded-xl border border-border bg-background p-3 shadow-lg">
              <div class="flex items-center gap-2 text-xs">
                <select v-model="historyCleanup.mode" class="select h-8 min-w-0 flex-1" aria-label="历史清理方式"
                  :disabled="isScanning || historyLoading">
                  <option value="count">按数量保留</option>
                  <option value="days">按天数保留</option>
                </select>
                <input v-model.number="historyCleanup.value" class="input h-8 w-20" type="number" min="0"
                  :max="historyCleanup.mode === 'count' ? 1000 : 3650" aria-label="历史清理保留值"
                  :disabled="isScanning || historyLoading">
                <span class="whitespace-nowrap text-muted-foreground">{{ historyCleanup.mode === 'count' ? '条' : '天' }}</span>
              </div>
              <p class="mt-2 text-xs text-muted-foreground">任意策略填 0 都会清空本页全部非置顶记录；要全部清空，请先取消置顶。</p>
              <button type="button" class="btn btn-danger mt-3 h-8 w-full px-3 text-xs"
                :disabled="isScanning || historyLoading || historyCleanup.running"
                @click="cleanupHistory">
                <MIcon name="delete_forever" :size="17" />{{ historyCleanup.running ? '清理中…' : '执行清理' }}
              </button>
            </div>
          </details>
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
          <span v-if="scan.total">已分析 {{ scan.scanned }}/{{ scan.total }} 个 · 命中 {{ results.length }} 个</span>
          <span v-else>正在准备币池，读的是本地库，通常几秒钟</span>
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
          点击「开始扫描」，或在右上角选一次历史扫描。永续合约 7×24 交易，最新一根 1 小时线可能还没走完，振幅偏小，容易被当成十字星。
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
            title="放宽的规则组里本来就含着严格组选出的交易对。勾上之后，每个交易对只归到第一个命中它的组，后面的组只剩自己新捞出来的。把严格的组排在前面，效果最好。">
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
          命中数超过返回上限，另有 {{ scan.stats.truncated }} 个没有返回（统计数字仍是完整的）。把规则收紧一些再扫可以看到全部。
        </p>
        <p v-if="staleWarning" class="border-b border-border px-5 py-2.5 text-xs text-destructive sm:px-6" role="alert">
          <MIcon name="warning" :size="16" class="mr-1 align-[-3px]" />超过一半的交易对在扫描日没有 1 小时线，多半是本地行情还没同步到这一天，建议先到「数据管理」页同步。
        </p>
      </template>

      <p v-if="scan.stats?.skipped?.gap" class="mx-5 my-3 rounded-lg border border-border p-3 text-sm" role="status">
        有 {{ scan.stats.skipped.gap }} 个标的因分析窗口行情不连续被跳过，可能是停牌或漏同步。请到「数据」页检查缺失区间并补拉；放宽形态阈值不能修复数据缺口。
      </p>

      <!-- 无结果 -->
      <div v-if="(scan.status === 'completed' || scan.status === 'cancelled') && !results.length"
        class="px-5 py-12 text-center sm:px-6">
        <span class="empty-icon"><MIcon name="search_off" :size="36" /></span>
        <p class="mt-4 text-title-m">没有找到处在横盘箱体里的交易对</p>
        <p v-if="!scan.stats?.skipped?.gap" class="mx-auto mt-1 max-w-lg text-sm text-muted-foreground">
          几组规则都没有出票。加密波动比 A 股大，箱体宽度可以放到 6%–10% 再试；也可以减少回验根数，或换一个扫描日。
        </p>
      </div>

      <!-- 结果列表 -->
      <template v-if="results.length">
        <p class="border-b border-border px-5 py-2.5 text-xs text-muted-foreground sm:px-6">
          {{ averageWindowLabel }}成交额分布（{{ basisLabel }}）：
          <template v-for="(bucket, i) in amountBuckets" :key="bucket.label">
            {{ i ? ' · ' : '' }}{{ bucket.label }} <span class="font-medium text-foreground">{{ bucket.count }}</span>
          </template>
        </p>

        <div class="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3 sm:px-6">
          <div v-if="!isTolerantRule && !isMaFlatRule && !isBollRule" class="seg" role="group" aria-label="越界口径">
            <button v-for="(item, key) in BASIS" :key="key" type="button" :title="item.desc"
              :class="['seg-btn', basis === key && 'is-active']" :aria-pressed="basis === key" @click="basis = key">
              {{ item.label }} {{ ruleCount(activeRuleId, key) }}
            </button>
          </div>
          <div v-if="supportsAnchorModes" class="seg" role="group" aria-label="命中模式">
            <button v-for="option in MODE_FILTERS" :key="option.value" type="button"
              :class="['seg-btn', modeFilter === option.value && 'is-active']" :aria-pressed="modeFilter === option.value"
              @click="modeFilter = option.value">
              {{ option.label }} {{ modeCount(option.value) }}
            </button>
          </div>
          <div class="relative w-full sm:w-44">
            <MIcon name="search" :size="18" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-md-on-surface-variant" />
            <input v-model.trim="keyword" class="input h-9 pl-8" type="search" placeholder="搜索交易对"
              aria-label="搜索交易对">
          </div>
          <select v-model="category" class="select" aria-label="按类别筛选">
            <option value="">全部类别（{{ basisResults.length }}）</option>
            <option v-for="item in categoryOptions" :key="item.name" :value="item.name">
              {{ item.name }}（{{ item.count }}）
            </option>
          </select>
          <div class="ml-auto flex items-center gap-2">
            <select v-model="sortBy" class="select" aria-label="排序方式">
              <option v-for="(item, key) in SORTS" :key="key" :value="key">{{ item.label }}</option>
            </select>
            <select v-model.number="pageSize" class="select" aria-label="每页个数">
              <option :value="12">每页 12</option>
              <option :value="24">每页 24</option>
              <option :value="48">每页 48</option>
            </select>
          </div>
        </div>

        <div v-if="!filteredResults.length" class="px-5 py-12 text-center sm:px-6">
          <p class="text-sm font-medium">这一组规则下没有匹配的交易对</p>
          <button v-if="basis === 'full' && !basisResults.length && ruleCount(activeRuleId, 'body')" type="button"
            class="btn-quiet mt-3 h-8 px-3" @click="basis = 'body'">
            切换到实体口径（{{ ruleCount(activeRuleId, 'body') }} 个）
          </button>
          <button v-else type="button" class="btn-quiet mt-3 h-8 px-3" @click="clearFilters">清除筛选</button>
        </div>

        <div v-else class="grid gap-4 p-4 sm:p-6 lg:grid-cols-2">
          <article v-for="(item, i) in pagedResults" :key="item.symbol" class="result-card lift rise-in" :style="{ '--i': i }">
            <header class="flex items-start justify-between gap-3 px-4 pt-3">
              <div class="min-w-0">
                <div class="flex items-baseline gap-2">
                  <h3 class="truncate text-title-m">{{ item.base_asset }}</h3>
                  <span class="shrink-0 font-mono text-xs text-muted-foreground">{{ item.symbol }}</span>
                </div>
                <div class="mt-1 flex flex-wrap gap-1.5">
                  <span :class="['tag', item.match.mode === 'doji' && 'tag-primary']">
                    {{ MODES[item.match.mode].label }}
                  </span>
                  <span class="tag">{{ item.category_label }}</span>
                  <span class="tag" title="24 小时成交额">24h {{ fmtAmount(item.quote_volume) }}</span>
                  <span v-if="!item.match.passed_full" class="tag">仅实体口径入选</span>
                  <span v-if="item.otherRules.length" class="tag" :title="`同时命中：${item.otherRules.join('、')}`">
                    另命中 {{ item.otherRules.length }} 组
                  </span>
                </div>
              </div>
              <div class="flex shrink-0 gap-1.5">
                <button type="button" class="btn-quiet h-8 px-2.5" @click="openChart(item)">
                  <MIcon name="open_in_full" :size="16" />大图
                </button>
                <button type="button" class="btn-quiet h-8 px-2.5" :disabled="!!caseState[caseKey(item)]"
                  @click="saveToCases(item)">
                  <MIcon :name="caseState[caseKey(item)] === 'saved' ? 'bookmark_added' : 'bookmark_add'" :size="16" />
                  {{ caseState[caseKey(item)] === 'saved' ? '已存案例' : caseState[caseKey(item)] === 'saving' ? '保存中' : '存为案例' }}
                </button>
              </div>
            </header>

            <KlineChart :kline-url="item.kline_url" :klineData="item.kline_data" :markLines="item.markLines" :isDarkMode="isDarkMode"
              :ma-period="item.match.ma_period" :bollinger="item.match" height="200px" width="100%" class="mt-1" />

            <dl class="grid grid-cols-2 gap-x-4 gap-y-2 px-4 pb-4 pt-1 text-xs sm:grid-cols-3">
              <div>
                <dt class="text-muted-foreground">{{ item.match.mode === 'boll_box' ? (item.match.boll_geometry === 'endpoints_v1' ? '尾部上下轨' : '旧版轨道中位参考') : item.match.mode === 'ma_flat' ? '区间价格（仅展示）' : '箱体' }}</dt>
                <dd class="mt-0.5 font-medium">
                  {{ fmtPrice(item.match.lower) }} – {{ fmtPrice(item.match.upper) }}
                  <span class="text-muted-foreground">
                    · <template v-if="item.match.mode === 'amplitude'">箱高 {{ fmtPct(boxHeight(item.match)) }} · </template>实际震荡 {{ fmtPct(item.match.actual_range) }}
                  </span>
                </dd>
              </div>
              <div>
                <dt class="text-muted-foreground">收盘 · 涨幅 · 末端振幅</dt>
                <dd class="mt-0.5 font-medium">
                  {{ fmtPrice(item.close) }}
                  <span :class="lastChange(item) > 0 ? 'text-rise' : lastChange(item) < 0 ? 'text-fall' : ''">
                    {{ fmtSignedPct(lastChange(item)) }}
                  </span>
                  · {{ fmtPct(item.amplitude) }}
                </dd>
              </div>
              <div>
                <dt class="text-muted-foreground">{{ item.match.mode === 'boll_box' ? (item.match.boll_geometry === 'endpoints_v1' ? '首尾矩形偏差' : '旧版轨摆 · 带宽变化') : item.match.mode === 'ma_flat' ? '均线波动 · ER' : item.match.mode === 'tolerant' ? '刺破根数' : '越界根数' }}</dt>
                <dd v-if="item.match.mode === 'boll_box'" class="mt-0.5 font-medium">
                  <template v-if="item.match.boll_geometry === 'endpoints_v1'">{{ fmtPct(item.match.rectangle_error) }}</template>
                  <template v-else>{{ fmtPct(item.match.rail_range) }} · {{ fmtPct(item.match.bandwidth_range) }}</template>
                </dd>
                <dd v-else-if="item.match.mode === 'ma_flat'" class="mt-0.5 font-medium">
                  {{ fmtPct(item.match.ma_range) }} · {{ item.match.efficiency_ratio?.toFixed(3) }}
                </dd>
                <dd v-else-if="item.match.mode === 'tolerant'" class="mt-0.5 font-medium">
                  实体 {{ item.match.breach_body }} · 影线 {{ item.match.breach_full }} · 最长连续 {{ item.match.longest_consecutive_breach }}
                </dd>
                <dd v-else class="mt-0.5 font-medium">整体 {{ item.match.breach_full }} · 实体 {{ item.match.breach_body }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">{{ averageWindowLabel }}成交额</dt>
                <dd class="mt-0.5 font-medium">{{ fmtAmount(item.match.avg_amount) }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">{{ averageWindowLabel }}成交笔数</dt>
                <dd class="mt-0.5 font-medium">{{ fmtTrades(item.match.avg_trades) }}</dd>
              </div>
              <div>
                <dt class="text-muted-foreground">{{ item.match.mode === 'boll_box' ? '矩形起点' : item.match.mode === 'ma_flat' ? '均线走平起点' : '回验起点' }}</dt>
                <dd class="mt-0.5 font-medium">{{ item.match.lookback_start || '—' }}</dd>
              </div>
              <div v-if="item.match.mode === 'ma_flat'">
                <dt class="text-muted-foreground">MA{{ item.match.ma_period }} 连续走平</dt>
                <dd class="mt-0.5 font-medium" :title="item.match.history_limited ? '已到可用历史边界，实际持续时间可能更长' : ''">
                  {{ item.match.history_limited ? '至少 ' : '' }}{{ item.match.flat_bars }} 根
                </dd>
              </div>
              <div v-if="item.match.mode === 'ma_flat'">
                <dt class="text-muted-foreground">末端状态 · 距均线</dt>
                <dd class="mt-0.5 font-medium">{{ formatTailState(item.match) }} · {{ fmtSignedPct(item.match.price_ma_distance) }}</dd>
              </div>
              <template v-if="item.match.mode === 'boll_box'">
                <div v-if="item.match.boll_geometry === 'endpoints_v1'">
                  <dt class="text-muted-foreground">头部上下轨</dt>
                  <dd class="mt-0.5 font-medium">{{ fmtPrice(item.match.head_lower) }} – {{ fmtPrice(item.match.head_upper) }}</dd>
                </div>
                <div>
                  <dt class="text-muted-foreground">BOLL{{ item.match.boll_period }} × {{ item.match.boll_multiplier }} {{ item.match.boll_geometry === 'endpoints_v1' ? '首尾四点区间' : '旧版连续矩形' }}</dt>
                  <dd class="mt-0.5 font-medium">{{ item.match.history_limited ? '至少 ' : '' }}{{ item.match.box_bars }} 根
                    <span v-if="item.match.history_limited" class="text-muted-foreground"> · 历史受限</span>
                  </dd>
                </div>
                <div>
                  <dt class="text-muted-foreground">最新带宽 · 末端状态（仅提示）</dt>
                  <dd class="mt-0.5 font-medium">{{ fmtPct(item.match.bandwidth) }} · {{ formatTailState(item.match) }}</dd>
                </div>
              </template>
            </dl>
          </article>
        </div>

        <div v-if="totalPages > 1"
          class="flex items-center justify-between gap-3 border-t border-border px-5 py-3 text-sm sm:px-6">
          <span class="text-xs text-muted-foreground">第 {{ page }} / {{ totalPages }} 页，共 {{ filteredResults.length }} 个</span>
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
import { lastChangeRatio as lastChange } from '../scan/semantics.js';
import { defineAsyncComponent } from 'vue';
import HistorySaveStatus from '../components/HistorySaveStatus.vue';
import { useHistoryPersistence } from '../scan/useHistoryPersistence.js';
import { useScanPolling, scanStatus, fullRows } from '../scan/useScanPolling.js';
import { historySnapshot } from '../scan/session.js';
import HistoryLink from '../components/HistoryLink.vue';
/**
 * 横盘-U：末端锚定横盘箱体扫本地加密永续。
 *
 * 结构、交互和横盘-A（HengpanScanView.vue）一一对应，箱体规则、规则组存储、
 * 规则编辑器都直接复用那边的模块，两页的判定口径因此始终一致。
 * 差别只在表字段：交易对代替股票代码、类别代替板块、成交额是 USDT、
 * 没有换手率和 ST，换成成交笔数和 24 小时成交额门槛；周期固定 1 小时线。
 */
import { shallowRef, ref, reactive, computed, watch, inject, onMounted, onActivated, onUnmounted, nextTick } from 'vue';
import axios from 'axios';
const KlineChart = defineAsyncComponent(() => import('../components/KlineChart.vue'));
const FullKlineChart = defineAsyncComponent(() => import('../components/FullKlineChart.vue'));
import RuleEditorTable from './rules/RuleEditorTable.vue';
import { deleteRuleGroup, loadRuleGroups, saveRuleGroup } from './ruleGroups.js';
import {
  BOX_MODES,
  DEFAULT_BOX_MODE,
  DEFAULT_RULES,
  PRESET_RULES,
  RULE_FIELDS,
  fieldsForMode,
  fieldEntriesForMode,
  fieldRangeError,
  formatTailState,
  formatRuleSummary,
  formatPayloadRuleSummary,
  normalizeRule,
  payloadToRule,
  ruleToPayload,
  rulesForMode,
  sameRule,
} from './ruleModes.js';

const isDarkMode = inject('isDarkMode');

const API = '/api/crypto/hengpan/scan';
const MAX_RULES = 6;
// 本地加密库目前只存 1 小时线，加周期要先在 api/crypto/db.py 的 INTERVALS 里登记
const FREQUENCY_LABEL = '1 小时 K 线';
// Hero 插图：一段横盘震荡的 K 线，[影线上端, 影线下端, 实体上沿, 实体高度]，最后一根是收窄的末端 K 线
const HERO_CANDLES = [
  [44, 86, 52, 24], [48, 84, 56, 20], [42, 80, 50, 22], [50, 88, 58, 22], [46, 82, 54, 18], [44, 86, 50, 28],
  [48, 84, 58, 18], [42, 82, 52, 22], [50, 86, 56, 24], [46, 80, 54, 18], [44, 84, 52, 24], [56, 72, 60, 8],
];

// 两类永续波动差好几倍，后端按类别分表存，这里也分开筛
const CATEGORIES = [
  { key: 'perpetual', label: '加密永续' },
  { key: 'tradifi', label: 'TradFi 永续' },
];

const MODES = {
  ...BOX_MODES,
  doji: { label: '十字星 · 贴箱顶' },
  normal: { label: '普通 · 箱体中部' },
  amplitude: { label: '振幅模式' },
  tolerant: { label: '容刺箱体' },
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
    compare: (a, b) => ((b.match.box_bars ?? b.match.flat_bars ?? 0) - (a.match.box_bars ?? a.match.flat_bars ?? 0)) ||
      ((a.match.efficiency_ratio ?? 0) - (b.match.efficiency_ratio ?? 0)) ||
      ((a.match.rectangle_error ?? a.match.rail_range ?? 0) - (b.match.rectangle_error ?? b.match.rail_range ?? 0)) ||
      (b.match.passed_full - a.match.passed_full) ||
      ((a.match.mode === 'doji' ? 0 : 1) - (b.match.mode === 'doji' ? 0 : 1)) ||
      (a.match.breach_full - b.match.breach_full) || a.symbol.localeCompare(b.symbol),
  },
  matches: { label: '命中组数从多到少', compare: (a, b) => b.otherRules.length - a.otherRules.length },
  amount: { label: '区间成交额从高到低', compare: (a, b) => (b.match.avg_amount ?? -1) - (a.match.avg_amount ?? -1) },
  trades: { label: '区间成交笔数从高到低', compare: (a, b) => (b.match.avg_trades ?? -1) - (a.match.avg_trades ?? -1) },
  volume24h: { label: '24 小时成交额从高到低', compare: (a, b) => (b.quote_volume ?? -1) - (a.quote_volume ?? -1) },
};
// 每根 1 小时线的平均成交额（USDT）。实测大币每小时几百万，小币几万
const AMOUNT_BUCKETS = [
  { label: '10 万以下', max: 1e5 },
  { label: '10 万–50 万', max: 5e5 },
  { label: '50 万–200 万', max: 2e6 },
  { label: '200 万–1000 万', max: 1e7 },
  { label: '1000 万以上', max: Infinity },
];

const pad = (n) => String(n).padStart(2, '0');
const todayDate = new Date();
const today = `${todayDate.getFullYear()}-${pad(todayDate.getMonth() + 1)}-${pad(todayDate.getDate())}`;
const trim = (value) => Number(Number(value).toFixed(4));

// ---- 扫描设置 ----
const createDefaultConfig = () => ({
  rules: [{ ...DEFAULT_RULES[DEFAULT_BOX_MODE] }],
  scan_date: '',
  categories: ['perpetual'],
  min_quote_wan: 1000,
});
const config = reactive(createDefaultConfig());
const activeBoxType = ref(DEFAULT_BOX_MODE);
const activeRuleFields = computed(() =>
  fieldEntriesForMode(activeBoxType.value).map(([key, field]) => ({ key, ...field })));
const modeRuleSets = reactive(Object.fromEntries(
  Object.keys(BOX_MODES).map(mode => [mode, rulesForMode(mode)]),
));
const isDefaultRules = computed(() => config.rules.length === 1 &&
  sameRule(config.rules[0], DEFAULT_RULES[activeBoxType.value]));
const savedRuleGroups = ref([]);
const selectedRuleGroupId = ref('');

function setConfigRules (rules) {
  const normalized = (rules?.length ? rules : [DEFAULT_RULES[DEFAULT_BOX_MODE]]).map(rule => normalizeRule(rule));
  const mode = normalized[0].box_type;
  for (const key of Object.keys(BOX_MODES)) {
    const matching = normalized.filter(rule => rule.box_type === key);
    if (matching.length) modeRuleSets[key] = matching.map(rule => ({ ...rule }));
  }
  activeBoxType.value = mode;
  config.rules = modeRuleSets[mode].map(rule => ({ ...rule }));
}

function changeBoxType (event) {
  const nextMode = event.target.value;
  modeRuleSets[activeBoxType.value] = config.rules.map(rule => normalizeRule(rule, activeBoxType.value));
  activeBoxType.value = nextMode;
  config.rules = modeRuleSets[nextMode].map(rule => ({ ...rule }));
  selectedRuleGroupId.value = '';
  basis.value = 'full';
  modeFilter.value = '';
  formError.value = '';
}

function addRule () {
  if (config.rules.length < MAX_RULES) config.rules.push({ ...config.rules[config.rules.length - 1] });
}
function removeRule (index) {
  if (config.rules.length > 1) config.rules.splice(index, 1);
}
function resetRules () {
  config.rules = rulesForMode(activeBoxType.value);
}
function usePreset () {
  config.rules = rulesForMode(activeBoxType.value, PRESET_RULES[activeBoxType.value]);
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
  setConfigRules(group.rules);
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

const categoryLabel = (key) => CATEGORIES.find(item => item.key === key)?.label || key;
const scopeLabel = (categories) =>
  (categories && categories.length ? categories.map(categoryLabel).join('、') : '全部永续');
// 类别筛选 chip：点一下加入 / 移出
function toggleCategory (key) {
  config.categories = config.categories.includes(key)
    ? config.categories.filter((item) => item !== key)
    : [...config.categories, key];
}

const categoriesHint = computed(() => config.categories.length
  ? `将扫描：${scopeLabel(config.categories)}`
  : '未选择类别，将扫描全部本地永续（加密永续 + TradFi 永续）；两类波动差好几倍，同一套箱体参数出票数会差很多');
const heroDescription = computed(() => activeBoxType.value === 'boll_box'
  ? BOX_MODES.boll_box.description
  : activeBoxType.value === 'ma_flat'
  ? '从已收盘尾部向前找均线走平区间，过滤明显单边走势。均线周期与最少持续根数独立可调，不限定价格箱宽。'
  : activeBoxType.value === 'tolerant'
  ? `用${FREQUENCY_LABEL}实体中心寻找主体箱体，允许少量离散刺破，连续脱离直接淘汰。`
  : `用${FREQUENCY_LABEL}最新一根 K 线定箱体，再用它之前的 K 线验箱体。宁可漏选，不会错选。`);
const averageWindowLabel = computed(() => isBollRule.value ? '矩形区间平均' : isMaFlatRule.value ? '走平区间平均' : `${activeLookback.value} 根 K 线平均`);
const summaryText = computed(() => [
  `${config.rules.length} 组规则：${config.rules.map(formatRuleSummary).join('，')}`,
  FREQUENCY_LABEL,
  config.scan_date ? `扫描日 ${config.scan_date}` : '最新一天',
  scopeLabel(config.categories),
  config.min_quote_wan ? `24h ≥ ${fmtCount(config.min_quote_wan)} 万 USDT` : '成交额不限',
].join(' · '));

const formError = ref('');

function validate () {
  for (const [index, rule] of config.rules.entries()) {
    for (const key of fieldsForMode(rule.box_type)) {
      const field = RULE_FIELDS[key];
      const value = rule[key];
      if (field.optional && (value === null || value === '')) continue;
      if (typeof value !== 'number' || !Number.isFinite(value)) return `第 ${index + 1} 组：请填写「${field.label}」`;
      if (key === 'box_pct' && value < 0) return `第 ${index + 1} 组：箱体宽度不能为负数`;
      const rangeError = fieldRangeError(key, value);
      if (rangeError) return `第 ${index + 1} 组：${rangeError}`;
    }
    if (fieldsForMode(rule.box_type).some(key => RULE_FIELDS[key].integer && !Number.isInteger(rule[key]))) {
      return `第 ${index + 1} 组：均线周期、K 线根数与刺破根数应为整数`;
    }
    if (!['ma_flat', 'boll_box'].includes(rule.box_type) && rule.max_breach >= rule.lookback) return `第 ${index + 1} 组：允许越界根数应小于回验根数`;
    if (rule.box_type === 'tolerant' && rule.max_consecutive_breach >= rule.lookback) {
      return `第 ${index + 1} 组：连续刺破上限应小于回验根数`;
    }
    const twin = config.rules.findIndex(other => sameRule(other, rule));
    if (twin !== index) return `第 ${index + 1} 组与第 ${twin + 1} 组完全相同，请删掉重复的一组`;
  }
  if (config.scan_date && config.scan_date > today) return '扫描日不能晚于今天';
  const volume = Number(config.min_quote_wan);
  if (!Number.isFinite(volume) || volume < 0) return '24 小时成交额门槛不能是负数';
  return '';
}

function buildPayload () {
  return {
    rules: config.rules.map(ruleToPayload),
    scan_date: config.scan_date || null,
    categories: config.categories,
    min_quote_volume: Math.round(Number(config.min_quote_wan) * 1e4),
  };
}

// ---- 扫描任务 ----
const scan = reactive({
  status: 'idle', progress: 0, message: '', error: '', startedAt: 0, finishedAt: 0,
  scanned: 0, total: 0, scanDate: '', stats: null, rules: [], params: null,
});
const isScanning = computed(() => scan.status === 'running');
const results = shallowRef([]);
const activeRuleId = ref('1');
const currentTaskId = ref(null);
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
const historyCleanup = reactive({ mode: 'count', value: 20, running: false });

const ruleLabel = (rule) => formatPayloadRuleSummary(rule.params);
const ruleById = (id) => scan.rules.find(rule => rule.id === id);
// 多组规则时始终给切换按钮：某组 0 个也要能切过去看其他组的统计
const showRuleTabs = computed(() => scan.rules.length > 1 && scan.status !== 'failed');
const activeRule = computed(() => ruleById(activeRuleId.value) || scan.rules[0]);
const supportsAnchorModes = computed(() => (activeRule.value?.params.box_type || 'fixed') === 'fixed');
const isTolerantRule = computed(() => activeRule.value?.params.box_type === 'tolerant');
const isBollRule = computed(() => activeRule.value?.params.box_type === 'boll_box');
const isMaFlatRule = computed(() => activeRule.value?.params.box_type === 'ma_flat');
const activeLookback = computed(() => activeRule.value?.params.lookback ?? DEFAULT_RULES.fixed.lookback);
const activeRuleDetail = computed(() => {
  const params = activeRule.value?.params;
  if (!params) return '';
  if (params.box_type === 'boll_box') return `${formatPayloadRuleSummary(params)} · ${params.rectangle_tolerance == null ? '旧版整段轨道结果' : '首尾四点结果'} · 重新扫描采用一次中点复核、向前遇坏即停`;
  if (params.box_type === 'ma_flat') return `${formatRuleSummary(payloadToRule(params))} · 只用已收盘 K 线 · 末端脱离仅提示`;
  if (params.box_type === 'amplitude') {
    return `末端 K 线上下各延伸 ${trim(params.amp_multiple)} 倍振幅 · ` +
      `回验 ${params.lookback} 根 · 容错 ${params.max_breach} 根`;
  }
  if (params.box_type === 'tolerant') {
    return `实体中心定箱 · 箱宽 ${trim(params.box_height * 100)}% · ` +
      `${params.lookback} 根内允许 ${params.max_breach} 刺 · 连续不超过 ${params.max_consecutive_breach} 根`;
  }
  return `十字星 ≤ ${trim(params.doji_amplitude * 100)}% · 箱高 ${trim(params.box_height * 100)}% · ` +
    `回验 ${params.lookback} 根 · 容错 ${params.max_breach} 根`;
});

// 这个交易对在某一组规则下算不算入选。实体口径下 matches 里的都算，整体口径还要看 passed_full
const qualifies = (item, ruleId, which) => {
  const match = item.matches[ruleId];
  return !!match && (which === 'body' || match.passed_full);
};
// 这个交易对在当前口径下命中的全部规则编号，按规则填写的先后顺序
const matchedRules = (item, which) =>
  scan.rules.filter(rule => qualifies(item, rule.id, which)).map(rule => rule.id);
// 「只看本组新增」把每个交易对只归给第一个命中它的组：放宽的组本来就含着严格组选出的，
// 按先后顺序归属之后各组互不重复，加起来正好是全部命中数
const belongsHere = (item, ruleId, which) => matchedRules(item, which)[0] === ruleId;

// 每组规则的入选数。默认取后端统计：结果被上限截断时这个数字仍然完整；
// 「只看本组新增」下改成按已返回的结果现算，因为后端统计不区分交易对归属哪一组
function ruleCount (ruleId, which = basis.value, exclusive = exclusiveOnly.value) {
  if (exclusive) {
    return results.value.filter(item => belongsHere(item, ruleId, which)).length;
  }
  const stat = scan.stats?.rules?.[ruleId];
  if (stat) return which === 'body' ? stat.passed_body : stat.passed_full;
  return results.value.filter(item => qualifies(item, ruleId, which)).length;
}

function appendResults (items) {
  if (!Array.isArray(items) || !items.length) return;
  const existing = new Set(results.value.map(item => item.symbol));
  const fresh = items.filter(item => item && item.symbol && !existing.has(item.symbol));
  if (fresh.length) results.value = [...results.value, ...fresh];
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
  cancelRequested.value = false;
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
  resetCaseState();
  Object.assign(scan, {
    status: 'running', progress: 0, message: '正在提交扫描任务…', error: '', startedAt: Date.now(), finishedAt: 0,
    scanned: 0, total: 0, scanDate: '', stats: null, rules: [], params: payload,
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
    polling.start(data.task_id);
  } catch (e) {
    finish('failed', { message: `扫描任务提交失败：${e.response?.data?.detail || e.message}` });
  }
}

async function poll (taskId, context) {
  try {
    const { data } = await scanStatus(`${API}/status/${taskId}?since=${streamCursor}`, taskId, context);
    if (!context.current()) return;
    if (['completed', 'cancelled', 'failed'].includes(data.status)) historyPersistence.observe(taskId, data);
    scan.progress = data.progress;
    scan.message = data.message;
    scan.scanned = data.scanned || 0;
    scan.total = data.total || 0;
    if (typeof data.cancel_requested === 'boolean') cancelRequested.value = data.cancel_requested;
    if (data.scan_date) scan.scanDate = data.scan_date;
    if (data.stats) scan.stats = data.stats;
    if (data.rules && JSON.stringify(scan.rules) !== JSON.stringify(data.rules)) scan.rules = data.rules;

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
  return `${item.scan_date || '—'} · ${scopeLabel(item.categories)} · ${rules || '—'} · ${when}${status}`;
}

async function loadHistory () {
  if (!selectedHistoryId.value) return;
  historyLoading.value = true;
  try {
    const { data: snapshot } = await axios.get(`/api/history/${encodeURIComponent(selectedHistoryId.value)}`);
    const data = historySnapshot(snapshot);
    applySnapshot(data, '已加载历史扫描');
  } catch (e) {
    notify(`加载历史结果失败：${e.message}`, 'error');
  } finally {
    historyLoading.value = false;
  }
}

async function deleteSelectedHistory () {
  const historyId = selectedHistoryId.value;
  if (!historyId) return;
  const item = histories.value.find(record => record.history_id === historyId);
  const ok = window.confirm(`确定删除这份历史扫描吗？\n\n${formatHistoryLabel(item || { history_id: historyId })}`);
  if (!ok) return;
  historyLoading.value = true;
  try {
    await axios.delete(`${API}/history/${encodeURIComponent(historyId)}`);
    selectedHistoryId.value = '';
    notify('历史扫描已删除');
    await loadHistories();
  } catch (e) {
    notify(`删除历史扫描失败：${e.message}`, 'error');
  } finally {
    historyLoading.value = false;
  }
}

async function cleanupHistory () {
  const value = Number(historyCleanup.value);
  if (String(historyCleanup.value ?? '').trim() === '') {
    notify('请输入清理保留值', 'error');
    return;
  }
  if (!Number.isInteger(value) || value < 0) {
    notify('保留值须为 0 或正整数', 'error');
    return;
  }
  const label = historyCleanup.mode === 'count' ? `保留最新 ${value} 条` : `保留最近 ${value} 天`;
  const ok = window.confirm(`确定清理旧历史扫描吗？\n\n${label}，超出的历史快照将被永久删除。置顶记录受保护，不会被清理。`);
  if (!ok) return;
  historyCleanup.running = true;
  historyLoading.value = true;
  try {
    const payload = historyCleanup.mode === 'count' ? { keep_count: value } : { keep_days: value };
    const { data } = await axios.post(`${API}/history/cleanup`, payload);
    notify(`已清理 ${data.deleted || 0} 份历史扫描`);
    await loadHistories();
    if (selectedHistoryId.value && !histories.value.some(item => item.history_id === selectedHistoryId.value)) {
      selectedHistoryId.value = '';
    }
  } catch (e) {
    notify(`清理历史扫描失败：${e.message}`, 'error');
  } finally {
    historyCleanup.running = false;
    historyLoading.value = false;
  }
}

// 把一份快照（历史详情或导入的文件，格式相同）原样展示到本页
function applySnapshot (data, label) {
  historyPersistence.reset();
  const rules = data.rules || [];
  // 表单恢复成这次扫描用的规则，方便在此基础上调整后重扫
  if (rules.length) {
    setConfigRules(rules.map(rule => payloadToRule(rule.params)));
  }
  config.scan_date = data.params?.scan_date || '';
  config.categories = data.params?.categories || [];
  config.min_quote_wan = Math.round((data.params?.min_quote_volume || 0) / 1e4);
  resetCaseState();
  results.value = [];
  appendResults(data.results || []);
  Object.assign(scan, {
    status: data.status === 'cancelled' ? 'cancelled' : 'completed',
    progress: 100,
    message: `${label}：${results.value.length} 个交易对`,
    error: '',
    scanned: Number(data.scanned || 0),
    total: Number(data.total || 0),
    scanDate: data.scan_date || '',
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
const exporting = ref(false);
const canExport = computed(() => !exporting.value && ['completed', 'cancelled'].includes(scan.status) && scan.rules.length > 0);

// 导出的文件和后端历史快照同一格式，导入时直接复用 applySnapshot
async function exportResults () {
  if (exporting.value) return;
  exporting.value = true;
  try {
  const snapshot = {
    status: scan.status,
    message: scan.message,
    created_at: scan.startedAt / 1000,
    completed_at: scan.finishedAt / 1000,
    scan_date: scan.scanDate,
    frequency: '1h',
    params: scan.params,
    rules: scan.rules,
    stats: scan.stats,
    scanned: scan.scanned,
    total: scan.total,
    found: results.value.length,
    results: results.value,
  };
  const completeResults = [];
  for (const item of snapshot.results) {
    const { kline_url, ...hit } = item;
    completeResults.push({ ...hit, kline_data: await fullRows(item) });
  }
  snapshot.results = completeResults;
  const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `横盘U_${scan.scanDate || '未知日期'}_1小时_${results.value.length}个.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { notify(`导出失败：${e.message}`, 'error'); }
  finally { exporting.value = false; }
}

async function importResults (event) {
  const file = event.target.files?.[0];
  event.target.value = ''; // 允许重复选同一个文件
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (!Array.isArray(data?.rules) || !data.rules.length || !Array.isArray(data.results)) {
      throw new Error('不是横盘-U 导出的结果文件');
    }
    if (data.results.length && !data.results[0].symbol) {
      throw new Error('这是横盘-A 的结果文件，请在横盘-A 页面导入');
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
    { label: '数据周期', value: FREQUENCY_LABEL },
    { label: '已分析', value: fmtCount(scan.scanned), note: scan.total ? `共 ${fmtCount(scan.total)} 个` : '' },
    { label: '整体口径入选', value: fmtCount(ruleCount(activeRuleId.value, 'full', false)), note: note('full') },
    { label: '实体口径入选', value: fmtCount(ruleCount(activeRuleId.value, 'body', false)), note: note('body') },
    {
      label: '跳过',
      value: skipped ? fmtCount(skipped.stale + skipped.insufficient + skipped.failed + (skipped.gap || 0)) : '—',
      note: skipped ? `当日无 K 线 ${skipped.stale} · 数据不足 ${skipped.insufficient} · 窗口内缺口 ${skipped.gap || 0} · 读取失败 ${skipped.failed}` : '',
    },
    {
      label: '十字星分界附近',
      value: stat && supportsAnchorModes.value ? fmtCount(stat.near) : '—',
      note: supportsAnchorModes.value ? (stat ? `换一种模式能入选 ${stat.rescued} 个` : '') : '当前模式不区分十字星',
    },
  ];
});
// 大半交易对在扫描日没有 1 小时线，多半是本地行情没同步到这一天
const staleWarning = computed(() =>
  !!scan.stats && scan.scanned >= 50 && scan.stats.skipped.stale > scan.scanned / 2);

// ---- 结果筛选与分页 ----
const basis = ref('full');
const basisLabel = computed(() => isBollRule.value ? (activeRule.value?.params.rectangle_tolerance == null ? '旧版整段轨道' : '布林矩形 · 首尾四点') : isMaFlatRule.value ? '均线走平 · ER 过滤' :
  isTolerantRule.value ? '实体刺判定' : BASIS[basis.value].label);
const exclusiveOnly = ref(false); // 每个交易对只归第一个命中它的组，让各组互不重复
const modeFilter = ref('');
const keyword = ref('');
const category = ref('');
const sortBy = ref('default');
const pageSize = ref(12);
const page = ref(1);

function clearFilters () {
  modeFilter.value = '';
  keyword.value = '';
  category.value = '';
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
  if (match.boll_geometry === 'endpoints_v1') return [
    { date: match.lookback_start, text: '四点起点', color: '#3b82f6' },
    { date: match.box_end, text: '四点终点', color: '#3b82f6' },
  ];
  return [
    { type: 'horizontal', value: match.upper, text: match.mode === 'boll_box' ? '上轨中位参考' : match.mode === 'ma_flat' ? '区间最高' : '上轨', color: '#ec0000' },
    { type: 'horizontal', value: match.lower, text: match.mode === 'boll_box' ? '下轨中位参考' : match.mode === 'ma_flat' ? '区间最低' : '下轨', color: '#10b981' },
    { date: match.lookback_start, text: match.mode === 'boll_box' ? '矩形起点' : match.mode === 'ma_flat' ? '走平起点' : '回验起点', color: '#3b82f6' },
  ];
}

// 当前规则下命中的交易对，每个带上这一组的判定结果和标记线；
// 「只看本组新增」会滤掉同时命中别组的，让各组之间互不重复
const basisResults = computed(() => {
  const ruleId = activeRuleId.value;
  const which = basis.value;
  return results.value.flatMap(item => {
    if (!qualifies(item, ruleId, which)) return [];
    const others = matchedRules(item, which).filter(id => id !== ruleId);
    if (exclusiveOnly.value && !belongsHere(item, ruleId, which)) return [];
    return [{
      ...item,
      match: item.matches[ruleId],
      markLines: markLinesFor(item.matches[ruleId]),
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

const categoryOptions = computed(() => {
  const counter = {};
  basisResults.value.forEach(s => {
    const name = s.category_label || '未知类别';
    counter[name] = (counter[name] || 0) + 1;
  });
  return Object.entries(counter).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
});

const filteredResults = computed(() => {
  const kw = keyword.value.toLowerCase();
  return basisResults.value
    .filter(s =>
      (!supportsAnchorModes.value || !modeFilter.value || s.match.mode === modeFilter.value) &&
      (!category.value || (s.category_label || '未知类别') === category.value) &&
      (!kw || s.symbol.toLowerCase().includes(kw) || (s.base_asset || '').toLowerCase().includes(kw)))
    .sort(SORTS[sortBy.value].compare);
});
const totalPages = computed(() => Math.max(1, Math.ceil(filteredResults.value.length / pageSize.value)));
const pagedResults = computed(() =>
  filteredResults.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value));
watch([basis, exclusiveOnly, modeFilter, keyword, category, sortBy, pageSize, activeRuleId],
  () => { page.value = 1; });

function goPage (target) {
  page.value = Math.min(Math.max(1, target), totalPages.value);
  resultsRef.value?.scrollIntoView({ block: 'start' });
}

// ---- 格式化 ----
const fmtCount = (n) => Number(n || 0).toLocaleString('zh-CN');
// 加密价格跨好几个数量级：BTC 十万级、SHIB 小数点后七位，固定两位小数会把小币全显示成 0.00
const fmtPrice = (v) => {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toFixed(2);
  if (abs >= 1) return v.toFixed(4);
  if (abs >= 0.01) return v.toFixed(6);
  return v.toPrecision(4);
};
const fmtPct = (v) => (typeof v === 'number' ? `${(v * 100).toFixed(2)}%` : '—');
const fmtSignedPct = (v) => (Number.isFinite(v) ? `${v > 0 ? '+' : ''}${(v * 100).toFixed(2)}%` : '—');
// 末端 K 线的涨幅：相对上一根的收盘价

// 成交额单位是 USDT
const fmtAmount = (v) => {
  const value = Number(v);
  if (!Number.isFinite(value)) return '—';
  if (value >= 1e8) return `${(value / 1e8).toFixed(2)} 亿`;
  if (value >= 1e4) return `${(value / 1e4).toFixed(1)} 万`;
  return value.toFixed(0);
};
const fmtTrades = (v) => {
  const value = Number(v);
  if (!Number.isFinite(value)) return '—';
  return value >= 1e4 ? `${(value / 1e4).toFixed(1)} 万笔` : `${Math.round(value).toLocaleString('zh-CN')} 笔`;
};
// 振幅模式的箱高随末端 K 线变化，按和「实际震荡」相同的口径（除以最低价）现算
const boxHeight = (match) => (match.lower > 0 ? (match.upper - match.lower) / match.lower : null);

// ---- 大图与提示 ----
const showFullChart = ref(false);
const chartSymbol = shallowRef(null);
watch(showFullChart, visible => { if (!visible) chartSymbol.value = null; });
const chartTitle = computed(() => {
  const item = chartSymbol.value;
  if (!item) return '';
  const rule = activeRule.value ? ` · ${ruleLabel(activeRule.value)}` : '';
  return `${item.base_asset}（${item.symbol}）· ${MODES[item.match.mode].label}${rule}`;
});
const chartMarkLines = computed(() => chartSymbol.value?.markLines || []);

function openChart (item) {
  chartSymbol.value = item;
  showFullChart.value = true;
}

const notice = ref(null);
let noticeTimer = null;
function notify (text, type = 'info') {
  notice.value = { text, type };
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { notice.value = null; }, 3000);
}

// ---- 存为案例 ----
// 同一个交易对在不同规则组下箱体不同，可以各存一份，所以按「规则组 + 交易对」记状态
const caseState = reactive({}); // `${ruleId}:${symbol}` -> 'saving' | 'saved'
const caseKey = (item) => `${activeRuleId.value}:${item.symbol}`;
// 换一批结果就把按钮状态清掉：箱体已经变了，旧的「已存案例」不该再拦着
let caseGeneration = 0;
function resetCaseState () {
  caseGeneration++;
  Object.keys(caseState).forEach(key => { delete caseState[key]; });
}

// 横盘规则没有「窗口期」概念，用回验根数顶上；箱体上下轨当阻力位与支撑位，案例详情页就能画出来
async function saveToCases (item) {
  const key = caseKey(item);
  if (caseState[key]) return;
  const generation = caseGeneration;
  caseState[key] = 'saving';
  const match = item.match;
  const lookback = match.box_bars ?? match.flat_bars ?? activeRule.value?.params.lookback ?? 0;
  const reason = match.boll_geometry === 'endpoints_v1'
    ? `BOLL${match.boll_period}(×${match.boll_multiplier}) 首尾四点 ${lookback} 根 · 矩形偏差 ${fmtPct(match.rectangle_error)} · ${formatTailState(match)}`
    : match.mode === 'boll_box'
    ? `BOLL${match.boll_period}(×${match.boll_multiplier}) 矩形 ${match.history_limited ? '至少 ' : ''}${lookback} 根 · 轨摆 ${fmtPct(match.rail_range)} · 带宽变化 ${fmtPct(match.bandwidth_range)} · ${formatTailState(match)}`
    : match.mode === 'ma_flat'
    ? `MA${match.ma_period} 走平 ${match.history_limited ? '至少 ' : ''}${lookback} 根 · 均线波动 ${fmtPct(match.ma_range)} · ER ${match.efficiency_ratio.toFixed(3)} · ${formatTailState(match)}`
    : `${MODES[match.mode].label} · 箱体 ${fmtPrice(match.lower)}–${fmtPrice(match.upper)} · ` +
    `实际震荡 ${fmtPct(match.actual_range)} · 回验 ${lookback} 根`;
  try {
    await axios.post('/api/cases/export', {
      stockData: { code: item.symbol, name: item.base_asset, industry: item.category_label || '未知类别' },
      analysisResult: {
        is_platform: true,
        platform_windows: [lookback],
        selection_reasons: { [lookback]: reason },
        // 用发起扫描时的参数，而不是之后改动过的表单
        parameters: { ...(scan.params || buildPayload()), windows: [lookback],
          ...(match.ma_period ? { ma_period: match.ma_period } : {}),
          ...(match.mode === 'boll_box' ? { bollinger: { ...match } } : {}) },
        mark_lines: item.markLines || [],
        box_analysis: { is_box_pattern: match.mode !== 'ma_flat', support_levels: [match.lower], resistance_levels: [match.upper] },
      },
      klineData: await fullRows(item),
    });
    if (generation === caseGeneration) caseState[key] = 'saved';
    notify(`已存为案例：${item.base_asset}`);
  } catch (e) {
    if (generation === caseGeneration) delete caseState[key];
    notify(`存为案例失败：${e.message}`, 'error');
  }
}

onActivated(loadHistories);
onMounted(() => {
  savedRuleGroups.value = loadRuleGroups(window.localStorage);
});
</script>

<style scoped>
/* 与 HengpanScanView.vue 同一套外观。scoped 样式不能跨组件共用，两页各带一份。 */
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
