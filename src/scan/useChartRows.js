import { ref, shallowRef, computed, watch, onActivated, onDeactivated, onUnmounted } from 'vue';
import axios from 'axios';
import { latestBars } from '../components/klineWindow.js';
// Rows belong to the displayed chart only; no global cache or mutation of scan results.
export function useChartRows (props, visible = () => true) {
  const active = ref(true), loaded = shallowRef([]), error = ref('');
  const rows = computed(() => latestBars(props.klineData?.length ? props.klineData : loaded.value, props.visibleBars));
  let controller, version = 0;
  function clear () { ++version; controller?.abort(); controller = null; loaded.value = []; }
  watch([() => props.klineUrl, () => props.klineData, visible, active], async () => {
    clear(); error.value = '';
    if (!active.value || !visible() || props.klineData?.length || !props.klineUrl) return;
    const token = version; controller = new AbortController();
    try {
      const { data } = await axios.get(props.klineUrl, { signal: controller.signal, timeout: 30000 });
      if (token === version) loaded.value = data.kline_data || [];
    } catch (e) { if (token === version && !axios.isCancel(e)) error.value = 'K 线加载失败，请重新打开'; }
  }, { immediate: true });
  onActivated(() => { active.value = true; });
  onDeactivated(() => { active.value = false; clear(); });
  onUnmounted(clear);
  return { rows, active, error };
}
