/**
 * 全局反馈：Snackbar 提示条和确认对话框（M3 样式，替代浏览器原生 confirm/alert）。
 *   const { notify, confirm } = useFeedback();
 *   notify('已删除 176 根 K 线');                       // 底部提示条，4 秒后消失
 *   notify('同步失败：…', { tone: 'error' });
 *   if (await confirm({ title: '清空创业板？', message: '…', confirmText: '清空', danger: true })) { … }
 * 渲染由 App.vue 里的 <FeedbackHost /> 负责。
 */
import { reactive } from 'vue';

export const feedbackState = reactive({
  snackbar: null,      // { id, message, tone, action }
  dialog: null,        // { title, message, confirmText, cancelText, danger, icon, resolve }
});

let snackbarTimer = null;
let snackbarId = 0;

function notify (message, { tone = 'info', duration = 4000, action = null } = {}) {
  clearTimeout(snackbarTimer);
  feedbackState.snackbar = { id: ++snackbarId, message, tone, action };
  if (duration > 0) snackbarTimer = setTimeout(() => { feedbackState.snackbar = null; }, duration);
}

function dismiss () {
  clearTimeout(snackbarTimer);
  feedbackState.snackbar = null;
}

function confirm ({ title, message = '', confirmText = '确定', cancelText = '取消', danger = false, icon = null } = {}) {
  return new Promise((resolve) => {
    feedbackState.dialog = { title, message, confirmText, cancelText, danger, icon, resolve };
  });
}

function settle (result) {
  const dialog = feedbackState.dialog;
  feedbackState.dialog = null;
  if (dialog) dialog.resolve(result);
}

export function useFeedback () {
  return { notify, dismiss, confirm, settle };
}
