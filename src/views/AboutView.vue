<template>
  <main class="mx-auto max-w-6xl px-6 py-10 lg:px-10 lg:py-14">
    <header class="about-header">
      <div class="app-mark" aria-hidden="true">
        <MIcon name="stacked_line_chart" filled :size="32" />
      </div>
      <div>
        <p class="text-label-l text-md-primary">A 股与加密市场研究工具</p>
        <h2 class="mt-2 text-headline-m">平台期扫描系统</h2>
        <p class="mt-3 max-w-3xl text-body-l text-md-on-surface-variant">
          面向本地行情数据的形态扫描与复盘工作台，用于发现 A 股和加密永续市场中的横盘蓄势、平台整理等结构，
          并集中查看扫描结果、K 线与历史记录。
        </p>
      </div>
    </header>

    <section class="mt-10 border-t border-md-outline-variant pt-8" aria-labelledby="capabilities-title">
      <h3 id="capabilities-title" class="text-title-l">扫描能力</h3>
      <div class="capability-grid mt-5">
        <article v-for="item in capabilities" :key="item.name" class="capability-item">
          <span class="capability-icon"><MIcon :name="item.icon" :size="21" /></span>
          <div>
            <h4 class="text-title-m">{{ item.name }}</h4>
            <p class="mt-1 text-body-m text-md-on-surface-variant">{{ item.description }}</p>
          </div>
        </article>
      </div>
    </section>

    <section class="mt-10 grid gap-8 border-t border-md-outline-variant pt-8 lg:grid-cols-[1fr_280px]">
      <div>
        <h3 class="text-title-l">系统组成</h3>
        <p class="mt-3 text-body-m leading-7 text-md-on-surface-variant">
          系统围绕本地行情库运行，提供数据管理、扫描任务与历史记录、结果筛选、K 线可视化、案例管理和 API 接口文档，
          便于在一个工作台内完成日常筛选与复盘。
        </p>
        <a class="knowledge-link" href="https://www.baostock.com/mainContent?file=stockKData.md"
          target="_blank" rel="noopener noreferrer">
          <span class="knowledge-icon"><MIcon name="menu_book" :size="24" /></span>
          <span>
            <strong>Baostock 知识库</strong>
            <small>A 股历史行情数据说明与接口参考</small>
          </span>
          <MIcon class="knowledge-arrow" name="open_in_new" :size="20" />
        </a>
        <p class="mt-4 text-body-s text-md-on-surface-variant">
          本系统仅作为数据分析和研究辅助工具，不构成任何投资建议。
        </p>
        <a class="reference-link" href="https://github.com/24mlight/a-share-platform-stocks-selection"
          target="_blank" rel="noopener noreferrer">
          平台扫描功能参考
          <MIcon name="open_in_new" :size="14" />
        </a>
      </div>

      <dl class="version-panel">
        <div>
          <dt>作者</dt>
          <dd>熊猫吃竹子</dd>
        </div>
        <div>
          <dt>版本</dt>
          <dd>1.0.0</dd>
        </div>
        <div>
          <dt>运行方式</dt>
          <dd>本地部署</dd>
        </div>
        <div>
          <dt>覆盖市场</dt>
          <dd>A 股 · 加密永续</dd>
        </div>
      </dl>
    </section>

    <section class="guide-section" aria-labelledby="guide-title">
      <h3 id="guide-title" class="text-title-l">操作指南</h3>
      <ol class="guide-steps">
        <li>
          <span class="step-number">1</span>
          <div>
            <h4>同步数据</h4>
            <p>打开<a href="#/data">“数据”</a>，选择 A 股或加密货币，点击“开始同步”。数据库和数据表会自动创建。</p>
          </div>
        </li>
        <li>
          <span class="step-number">2</span>
          <div>
            <h4>运行扫描</h4>
            <p>进入横盘或平台页面，按需要调整条件，然后点击“开始扫描”。</p>
          </div>
        </li>
        <li>
          <span class="step-number">3</span>
          <div>
            <h4>查看与复盘</h4>
            <p>筛选扫描结果、查看 K 线，之后可从历史记录继续复盘。</p>
          </div>
        </li>
      </ol>
    </section>
  </main>
</template>

<script setup>
import MIcon from '../ui/MIcon.vue';

const capabilities = [
  { name: '横盘-A', icon: 'candlestick_chart', description: 'A 股末端锚定箱体扫描' },
  { name: '横盘-U', icon: 'radar', description: '加密永续末端锚定箱体扫描' },
  { name: '平台-A', icon: 'monitoring', description: 'A 股多窗口平台期识别' },
  { name: '平台-U', icon: 'token', description: '加密永续多窗口平台期识别' },
];
</script>

<style scoped>
.about-header {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.app-mark {
  display: grid;
  width: 64px;
  height: 64px;
  place-items: center;
  border-radius: 8px;
  background: var(--md-primary-container);
  color: var(--md-on-primary-container);
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border: 1px solid var(--md-outline-variant);
  border-radius: 8px;
  overflow: hidden;
}

.capability-item {
  display: flex;
  min-height: 112px;
  gap: 16px;
  padding: 24px;
}

.capability-item:nth-child(odd) { border-right: 1px solid var(--md-outline-variant); }
.capability-item:nth-child(-n + 2) { border-bottom: 1px solid var(--md-outline-variant); }

.capability-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  place-items: center;
  border-radius: 8px;
  background: var(--md-secondary-container);
  color: var(--md-on-secondary-container);
}

.knowledge-link {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) 24px;
  align-items: center;
  gap: 16px;
  margin-top: 24px;
  max-width: 620px;
  min-height: 88px;
  padding: 18px 20px;
  border: 1px solid var(--md-outline-variant);
  border-radius: 8px;
  background: var(--md-surface-container-low);
  color: var(--md-on-surface);
  text-decoration: none;
  transition: background-color var(--md-duration-short) var(--md-ease-standard),
    border-color var(--md-duration-short) var(--md-ease-standard);
}

.knowledge-link:hover {
  border-color: var(--md-primary);
  background: var(--md-primary-container);
}

.knowledge-link:focus-visible {
  outline: 2px solid var(--md-primary);
  outline-offset: 3px;
}

.knowledge-icon {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 8px;
  background: var(--md-tertiary-container);
  color: var(--md-on-tertiary-container);
}

.knowledge-link strong,
.knowledge-link small { display: block; }
.knowledge-link strong { font-size: 16px; font-weight: 600; }
.knowledge-link small { margin-top: 4px; color: var(--md-on-surface-variant); font-size: 13px; }
.knowledge-arrow { color: var(--md-on-surface-variant); }

.reference-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 12px;
  color: var(--md-on-surface-variant);
  font-size: 12px;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.reference-link:hover { color: var(--md-primary); text-decoration: underline; }
.reference-link:focus-visible { outline: 2px solid var(--md-primary); outline-offset: 3px; }

.version-panel {
  align-self: start;
  border-left: 3px solid var(--md-primary);
  padding-left: 20px;
}

.version-panel > div {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 12px;
  padding: 8px 0;
}

.version-panel dt {
  color: var(--md-on-surface-variant);
  font-size: 13px;
}

.version-panel dd {
  font-size: 14px;
  font-weight: 500;
}

.guide-section {
  margin-top: 40px;
  padding-top: 32px;
  border-top: 1px solid var(--md-outline-variant);
}

.guide-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 20px;
}

.guide-steps li {
  display: flex;
  gap: 14px;
  padding: 4px 28px;
  list-style: none;
}

.guide-steps li:first-child { padding-left: 0; }
.guide-steps li:not(:last-child) { border-right: 1px solid var(--md-outline-variant); }

.step-number {
  display: grid;
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  place-items: center;
  border-radius: 50%;
  background: var(--md-primary-container);
  color: var(--md-on-primary-container);
  font-size: 13px;
  font-weight: 700;
}

.guide-steps h4 { font-size: 15px; font-weight: 600; }
.guide-steps p { margin-top: 6px; color: var(--md-on-surface-variant); font-size: 13px; line-height: 1.65; }
.guide-steps a { color: var(--md-primary); text-decoration: underline; text-underline-offset: 3px; }

@media (max-width: 720px) {
  .about-header { grid-template-columns: 1fr; }
  .capability-grid { grid-template-columns: 1fr; }
  .capability-item:nth-child(odd) { border-right: 0; }
  .capability-item:not(:last-child) { border-bottom: 1px solid var(--md-outline-variant); }
  .guide-steps { grid-template-columns: 1fr; gap: 20px; }
  .guide-steps li { padding: 0 0 20px; }
  .guide-steps li:not(:last-child) { border-right: 0; border-bottom: 1px solid var(--md-outline-variant); }
}
</style>
