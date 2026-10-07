import { reactive, onUnmounted } from 'vue';
import axios from 'axios';
import { createHistoryPersistence } from './historyPersistence.js';
export function useHistoryPersistence (onSaved) {
  const state = reactive({});
  const actions = createHistoryPersistence(state, axios, onSaved);
  onUnmounted(actions.reset);
  return { state, ...actions };
}
