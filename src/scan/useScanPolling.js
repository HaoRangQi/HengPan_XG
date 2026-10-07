import { onUnmounted } from 'vue';
import axios from 'axios';
import { createPollingSession, drainResults } from './session.js';
export function useScanPolling (tick, delay = 2000) {
  let taskId = null;
  const session = createPollingSession(context => tick(taskId, context), delay);
  const visibility = () => { if (document.hidden) session.stop(); else if (taskId) session.start(); };
  document.addEventListener('visibilitychange', visibility);
  onUnmounted(() => { taskId = null; session.stop(); document.removeEventListener('visibilitychange', visibility); });
  return { start (id) { taskId = id; if (!document.hidden) session.start(); }, stop () { taskId = null; session.stop(); } };
}
export async function scanStatus (url, taskId, context) {
  const options = { signal: context.signal, timeout: 30000 };
  let data;
  try { ({ data } = await axios.get(`${url}${url.includes('?') ? '&' : '?'}compact=true`, options)); }
  catch (error) {
    if (error.response?.status !== 404) throw error;
    ({ data } = await axios.get(`/api/tasks/${encodeURIComponent(taskId)}/status`, options));
  }
  if (['completed', 'cancelled', 'failed'].includes(data.status)) data.result = await drainResults(taskId, axios.get, options);
  return { data };
}
export async function fullRows (stock) {
  if (stock?.kline_data?.length) return stock.kline_data;
  if (!stock?.kline_url) return [];
  const { data } = await axios.get(stock.kline_url, { timeout: 30000 });
  return data.kline_data || [];
}
