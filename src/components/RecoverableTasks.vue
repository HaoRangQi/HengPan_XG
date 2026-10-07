<template>
  <section v-if="tasks.length || error" class="mb-4 rounded-lg border border-border p-4" aria-label="待恢复的扫描结果">
    <h2 class="font-semibold">待恢复的扫描结果</h2>
    <p class="text-sm text-muted-foreground">这些结果仍在本机缓存中，保存到历史后即可正常查看。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <div v-for="task in tasks" :key="task.task_id" class="mt-3 flex flex-wrap items-center gap-3">
      <span>{{ task.message }} · {{ task.found }} 个结果</span>
      <span v-if="task.error" class="text-sm" role="status">{{ task.error }}</span>
      <button class="btn btn-outline" :disabled="busy === task.task_id" @click="retry(task)">{{ busy === task.task_id ? '正在保存…' : '保存到历史' }}</button>
    </div>
  </section>
</template>
<script setup>
import { ref, onMounted, onActivated } from 'vue';
import axios from 'axios';
const emit = defineEmits(['saved']);
const tasks = ref([]), error = ref(''), busy = ref(null);
let loading = false;
async function load () {
  if (loading) return;
  loading = true;
  try { tasks.value = (await axios.get('/api/tasks/recoverable', { timeout: 10000 })).data.tasks; error.value = ''; }
  catch { error.value = '暂时无法检查待恢复任务'; }
  finally { loading = false; }
}
async function retry (task) {
  busy.value = task.task_id;
  try {
    await axios.post(`/api/tasks/${encodeURIComponent(task.task_id)}/history/retry`, {}, { timeout: 60000 });
    await load(); emit('saved');
  } catch (e) { error.value = e.response?.data?.detail || '保存失败，缓存仍保留'; }
  finally { busy.value = null; }
}
onMounted(load); onActivated(load);
</script>
