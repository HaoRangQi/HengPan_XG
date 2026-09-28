import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('参数提示直接使用主题角色并保持实色高对比', async () => {
  const source = await readFile(new URL('./ParameterTooltip.vue', import.meta.url), 'utf8');

  assert.doesNotMatch(source, /hsl\(var\(--(?:primary|foreground)\)/);
  assert.match(source, /background:\s*var\(--md-inverse-surface\)/);
  assert.match(source, /color:\s*var\(--md-inverse-on-surface\)/);
  assert.doesNotMatch(source, /background-color:\s*rgba\(255,\s*255,\s*255,\s*0\.15\)/);
});
