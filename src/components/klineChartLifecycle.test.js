import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('KlineChart 将 ECharts 容器与 Vue 加载层分开管理', async () => {
  const source = await readFile(new URL('./KlineChart.vue', import.meta.url), 'utf8');

  assert.match(
    source,
    /class="chart-wrapper relative"[^>]*>\s*<div ref="chartRef" class="h-full w-full"><\/div>\s*(?:<!--[\s\S]*?-->\s*)?<div v-if="loading"/
  );
});
