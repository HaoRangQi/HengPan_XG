// Terminal scan results and durable history are separate transitions. Confirm once,
// then leave an explicit retry action instead of an indefinite background poll.
export function createHistoryPersistence (state, http, onSaved = () => {}, schedule = setTimeout, cancel = clearTimeout) {
  let version = 0, timer, controller;
  function reset () {
    ++version; cancel(timer); controller?.abort(); controller = null;
    Object.assign(state, { taskId: null, status: 'idle', error: '', busy: false });
  }
  function apply (data) {
    state.error = data.history_error || '';
    state.status = data.saved || data.history_id ? 'saved' : state.error ? 'failed' : 'pending';
    if (state.status === 'saved') onSaved();
  }
  async function request (retry) {
    if (!state.taskId || state.busy) return;
    const token = version;
    controller = new AbortController(); state.busy = true;
    const options = { signal: controller.signal, timeout: 30000 };
    try {
      const url = `/api/tasks/${encodeURIComponent(state.taskId)}`;
      const { data } = retry ? await http.post(`${url}/history/retry`, {}, options) : await http.get(`${url}/status`, options);
      if (token === version) apply(data);
    } catch (error) {
      if (token !== version) return;
      state.status = 'failed';
      state.error = typeof error.response?.data?.detail === 'string' ? error.response.data.detail : error.message;
    } finally { if (token === version) state.busy = false; }
  }
  function observe (taskId, data) {
    reset(); state.taskId = taskId; apply(data);
    if (state.status === 'pending') timer = schedule(() => { void request(false); }, 1000);
  }
  reset();
  return { reset, observe, retry: () => { cancel(timer); return request(true); } };
}
