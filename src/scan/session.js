export function createPollingSession (tick, delay = 2000, onError = error => console.error('扫描轮询失败:', error)) {
  let generation = 0, timer, controller;
  function stop () { ++generation; clearTimeout(timer); controller?.abort(); controller = null; }
  function start () {
    stop(); const token = generation;
    async function run () {
      if (token !== generation) return;
      controller = new AbortController();
      const current = () => token === generation;
      try { await tick({ signal: controller.signal, current }); }
      catch (error) { if (current()) onError(error); }
      finally { if (current()) timer = setTimeout(run, delay); }
    }
    void run();
  }
  return { start, stop };
}
export async function drainResults (taskId, get, options = {}) {
  let offset = 0; const results = [];
  do {
    const { data } = await get(`/api/tasks/${encodeURIComponent(taskId)}/results?offset=${offset}&limit=100`, options);
    results.push(...data.results);
    const next = data.next_offset;
    if (next == null) break;
    if (next <= offset) throw new Error('Invalid result cursor');
    offset = next;
  } while (true);
  return results;
}
export function historySnapshot (data) {
  const params = data.params || data.parameters || data.request || data.config || {};
  return { ...params, ...data, params, parameters: params, request: params,
    results: (data.results || []).map(hit => ({ ...hit, kline_url: `/api/history/${encodeURIComponent(data.run_id)}/kline/${encodeURIComponent(hit.code || hit.symbol)}` })) };
}
