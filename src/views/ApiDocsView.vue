<template>
  <main class="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
    <div class="mb-6">
      <h1 class="text-xl font-semibold">接口文档</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        根据后端自动生成的接口描述渲染，与代码保持同步。开发环境下前端经 Vite 代理访问 <code class="code">/api</code>，
        后端直连地址为 <code class="code">http://127.0.0.1:18001</code>。
      </p>
    </div>

    <p v-if="loadError" class="rounded-lg border border-border bg-card px-5 py-6 text-sm text-destructive" role="alert">
      接口描述加载失败：{{ loadError }}
    </p>
    <p v-else-if="!spec" class="rounded-lg border border-border bg-card px-5 py-6 text-sm text-muted-foreground">加载中…</p>

    <div v-else class="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
      <!-- 目录 -->
      <nav class="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto" aria-label="接口目录">
        <div class="rounded-lg border border-border bg-card p-3">
          <p class="px-2 pb-2 pt-1 text-xs text-muted-foreground">{{ spec.info.title }} · 版本 {{ spec.info.version }}</p>
          <div v-for="group in groups" :key="group.tag" class="mt-2 first:mt-0">
            <p class="px-2 py-1 text-sm font-medium">{{ group.tag }}</p>
            <button v-for="op in group.ops" :key="op.id" type="button"
              class="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs hover:bg-foreground/5"
              @click="jump(op.id)">
              <span :class="['method w-12 shrink-0', METHOD_STYLES[op.method]]">{{ op.method.toUpperCase() }}</span>
              <span class="truncate text-muted-foreground">{{ op.summary }}</span>
            </button>
          </div>
          <p class="px-2 pb-1 pt-3 text-sm font-medium">
            <button type="button" class="hover:underline" @click="jump('models')">数据模型</button>
          </p>
        </div>
      </nav>

      <div class="min-w-0 space-y-6">
        <section v-for="group in groups" :key="group.tag" :aria-label="group.tag">
          <h2 class="mb-3 text-base font-semibold">{{ group.tag }}</h2>
          <div class="space-y-4">
            <article v-for="op in group.ops" :id="op.id" :key="op.id"
              class="scroll-mt-20 rounded-lg border border-border bg-card">
              <header class="border-b border-border px-5 py-4">
                <div class="flex flex-wrap items-center gap-3">
                  <span :class="['method', METHOD_STYLES[op.method]]">{{ op.method.toUpperCase() }}</span>
                  <code class="break-all font-mono text-sm">{{ op.path }}</code>
                </div>
                <h3 class="mt-2 text-sm font-semibold">{{ op.summary }}</h3>
                <p v-if="op.description" class="mt-1 text-sm text-muted-foreground">{{ op.description }}</p>
              </header>

              <div class="space-y-5 px-5 py-4 text-sm">
                <!-- 路径 / 查询参数 -->
                <div v-if="op.parameters.length">
                  <h4 class="block-title">请求参数</h4>
                  <div class="overflow-x-auto">
                    <table class="doc-table">
                      <thead>
                        <tr><th>参数</th><th>位置</th><th>类型</th><th>必填</th><th>默认值</th><th>说明</th></tr>
                      </thead>
                      <tbody>
                        <tr v-for="p in op.parameters" :key="p.in + p.name">
                          <td><code class="code">{{ p.name }}</code></td>
                          <td>{{ p.in === 'path' ? '路径' : p.in === 'query' ? '查询' : p.in }}</td>
                          <td><TypeLabel :parts="typeParts(p.schema)" @jump="jumpModel" /></td>
                          <td>{{ p.required ? '是' : '否' }}</td>
                          <td class="font-mono text-xs">{{ formatDefault(p.schema && p.schema.default) }}</td>
                          <td class="text-muted-foreground">{{ p.description || (p.schema && p.schema.description) || '—' }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- 请求体 -->
                <div v-if="op.body">
                  <h4 class="block-title">
                    请求体
                    <span class="font-normal text-muted-foreground">· JSON ·
                      <TypeLabel :parts="typeParts(op.body)" @jump="jumpModel" /></span>
                  </h4>
                  <FieldTable v-if="fieldsOf(op.body).length" :fields="fieldsOf(op.body)" :type-parts="typeParts"
                    :format-default="formatDefault" @jump="jumpModel" />
                  <p v-else class="text-muted-foreground">任意 JSON 对象，字段见上方说明。</p>
                  <details v-if="fieldsOf(op.body).length" class="mt-3">
                    <summary class="cursor-pointer text-xs text-muted-foreground hover:text-foreground">请求体示例</summary>
                    <pre class="mt-2 overflow-x-auto rounded-md bg-foreground/[0.05] p-3 font-mono text-xs leading-relaxed">{{ exampleOf(op.body) }}</pre>
                  </details>
                </div>

                <!-- 响应 -->
                <div>
                  <h4 class="block-title">响应</h4>
                  <ul class="space-y-1.5">
                    <li v-for="r in op.responses" :key="r.code" class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span :class="['font-mono text-xs font-medium', r.code < 300 ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive']">
                        {{ r.code }}
                      </span>
                      <span>{{ r.label }}</span>
                      <span v-if="r.schema" class="text-muted-foreground">
                        · <TypeLabel :parts="typeParts(r.schema)" @jump="jumpModel" />
                      </span>
                    </li>
                  </ul>
                </div>
              </div>
            </article>
          </div>
        </section>

        <!-- 数据模型 -->
        <section id="models" class="scroll-mt-20" aria-label="数据模型">
          <h2 class="mb-3 text-base font-semibold">数据模型</h2>
          <div class="space-y-4">
            <article v-for="name in modelNames" :id="`model-${name}`" :key="name"
              class="scroll-mt-20 rounded-lg border border-border bg-card px-5 py-4 text-sm">
              <h3 class="mb-3 font-mono text-sm font-semibold">{{ name }}</h3>
              <FieldTable :fields="fieldsOf({ $ref: `#/components/schemas/${name}` })" :type-parts="typeParts"
                :format-default="formatDefault" @jump="jumpModel" />
            </article>
          </div>
        </section>
      </div>
    </div>
  </main>
</template>

<script setup>
import { ref, computed, onMounted, h } from 'vue';
import axios from 'axios';

const METHOD_STYLES = {
  get: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  post: 'bg-sky-500/10 text-sky-700 dark:text-sky-400',
  put: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  delete: 'bg-red-500/10 text-red-700 dark:text-red-400',
};
const TYPE_NAMES = { string: '字符串', integer: '整数', number: '数值', boolean: '布尔', object: '对象', array: '数组' };
const STATUS_LABELS = { 200: '成功', 400: '请求有误', 404: '资源不存在', 422: '参数校验失败', 500: '服务器内部错误' };
// FastAPI 自动生成的英文描述，统一换成中文
const DEFAULT_DESCRIPTIONS = ['Successful Response', 'Validation Error'];
// 校验错误的结构由框架生成，不单独展示
const HIDDEN_MODELS = ['HTTPValidationError', 'ValidationError'];

const spec = ref(null);
const loadError = ref('');

const refName = (ref) => ref.split('/').pop();
const resolve = (schema) => (schema && schema.$ref ? spec.value.components.schemas[refName(schema.$ref)] : schema);

// 类型拆成若干片段，其中 ref 片段渲染为可跳转的模型名
function typeParts (schema) {
  if (!schema || !Object.keys(schema).length) return [{ text: '任意' }];
  if (schema.$ref) return [{ ref: refName(schema.$ref) }];
  const union = schema.anyOf || schema.oneOf;
  if (union) {
    const options = union.filter(u => u.type !== 'null');
    const parts = options.flatMap((u, i) => (i ? [{ text: ' 或 ' }] : []).concat(typeParts(u)));
    return options.length < union.length ? parts.concat({ text: '，可为空' }) : parts;
  }
  if (schema.type === 'array') return typeParts(schema.items).concat({ text: ' 数组' });
  const extra = schema.additionalProperties;
  if (schema.type === 'object' && extra && typeof extra === 'object' && Object.keys(extra).length) {
    return [{ text: '键值对（值为' }, ...typeParts(extra), { text: '）' }];
  }
  return [{ text: TYPE_NAMES[schema.type] || schema.type || '任意' }];
}

function fieldsOf (schema) {
  const s = resolve(schema);
  if (!s || !s.properties) return [];
  const required = new Set(s.required || []);
  return Object.entries(s.properties).map(([name, prop]) => ({
    name, schema: prop, required: required.has(name), default: prop.default, description: prop.description,
  }));
}

function formatDefault (value) {
  return value === undefined ? '—' : JSON.stringify(value);
}

function exampleOf (schema) {
  const PLACEHOLDERS = { string: '', integer: 0, number: 0, boolean: false, array: [], object: {} };
  const example = {};
  fieldsOf(schema).forEach(f => {
    if (f.default !== undefined) example[f.name] = f.default;
    else if (f.required) example[f.name] = PLACEHOLDERS[f.schema.type] ?? null;
  });
  return JSON.stringify(example, null, 2);
}

// 按标签分组，保持后端声明顺序
const groups = computed(() => {
  const map = new Map();
  Object.entries(spec.value.paths).forEach(([path, methods]) => {
    Object.entries(methods).forEach(([method, op]) => {
      const tag = (op.tags && op.tags[0]) || '其他';
      if (!map.has(tag)) map.set(tag, []);
      const content = op.requestBody && op.requestBody.content;
      map.get(tag).push({
        id: `op-${method}-${path.replace(/[^\w]+/g, '-')}`,
        method, path,
        summary: op.summary || path,
        description: op.description,
        parameters: op.parameters || [],
        body: content && content['application/json'] ? content['application/json'].schema : null,
        responses: Object.entries(op.responses || {}).map(([code, res]) => {
          const json = res.content && res.content['application/json'];
          return {
            code: Number(code),
            label: DEFAULT_DESCRIPTIONS.includes(res.description) || !res.description
              ? STATUS_LABELS[code] || '—' : res.description,
            schema: Number(code) < 300 && json && json.schema && Object.keys(json.schema).length ? json.schema : null,
          };
        }),
      });
    });
  });
  return [...map].map(([tag, ops]) => ({ tag, ops }));
});

const modelNames = computed(() =>
  Object.keys(spec.value.components?.schemas || {}).filter(name => !HIDDEN_MODELS.includes(name)));

// 页面用 hash 做路由，锚点跳转改用 scrollIntoView，避免改写地址栏
function jump (id) {
  document.getElementById(id)?.scrollIntoView({ block: 'start' });
}
const jumpModel = (name) => jump(`model-${name}`);

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/openapi.json');
    spec.value = data;
  } catch (e) {
    loadError.value = e.message;
  }
});

// 类型片段：模型名可点击跳到「数据模型」
const TypeLabel = (props, { emit }) => h('span', props.parts.map(part => (part.ref
  ? h('button', { type: 'button', class: 'font-mono text-xs text-sky-700 hover:underline dark:text-sky-400', onClick: () => emit('jump', part.ref) }, part.ref)
  : part.text)));
TypeLabel.props = ['parts'];
TypeLabel.emits = ['jump'];

const FieldTable = (props, { emit }) => h('div', { class: 'overflow-x-auto' }, h('table', { class: 'doc-table' }, [
  h('thead', h('tr', ['字段', '类型', '必填', '默认值', '说明'].map(t => h('th', t)))),
  h('tbody', props.fields.map(f => h('tr', { key: f.name }, [
    h('td', h('code', { class: 'code' }, f.name)),
    h('td', h(TypeLabel, { parts: props.typeParts(f.schema), onJump: name => emit('jump', name) })),
    h('td', f.required ? '是' : '否'),
    h('td', { class: 'font-mono text-xs' }, props.formatDefault(f.default)),
    h('td', { class: 'text-muted-foreground' }, f.description || '—'),
  ]))),
]));
FieldTable.props = ['fields', 'typeParts', 'formatDefault'];
FieldTable.emits = ['jump'];
</script>

<style scoped>
.method {
  @apply inline-block rounded px-1.5 py-0.5 text-center font-mono text-xs font-semibold;
}

.block-title {
  @apply mb-2 text-sm font-medium;
}

:deep(.code) {
  @apply rounded bg-foreground/[0.06] px-1 py-px font-mono text-xs;
}

:deep(.doc-table) {
  @apply w-full text-sm;
}

:deep(.doc-table th) {
  @apply whitespace-nowrap border-b border-border py-2 pr-4 text-left text-xs font-medium text-muted-foreground;
}

:deep(.doc-table td) {
  @apply border-b border-border py-2 pr-4 align-top;
}

:deep(.doc-table tbody tr:last-child td) {
  @apply border-b-0;
}
</style>
