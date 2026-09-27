const STORAGE_KEY = 'hengpan.rule-groups.v1';

function cloneRules (rules) {
  return (Array.isArray(rules) ? rules : []).map(rule => ({ ...rule }));
}

function readState (storage) {
  try {
    const parsed = JSON.parse(storage?.getItem(STORAGE_KEY) || 'null');
    if (Array.isArray(parsed)) {
      const groups = parsed.filter(group => group && Array.isArray(group.rules));
      return { nextNumber: groups.length + 1, groups };
    }
    if (parsed && Array.isArray(parsed.groups)) {
      return {
        nextNumber: Math.max(1, Number(parsed.nextNumber) || 1),
        groups: parsed.groups.filter(group => group && Array.isArray(group.rules)),
      };
    }
  } catch {
    // A corrupt browser value must not break the scan page.
  }
  return { nextNumber: 1, groups: [] };
}

function writeState (storage, state) {
  storage?.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function createDefaultHengpanConfig (defaultRule) {
  return {
    rules: [{ ...defaultRule }],
    frequency: '60',
    scan_date: '',
    markets: ['sh_main'],
  };
}

export function loadRuleGroups (storage) {
  return readState(storage).groups.map(group => ({ ...group, rules: cloneRules(group.rules) }));
}

export function saveRuleGroup (storage, currentGroups, rules) {
  const state = readState(storage);
  const number = state.nextNumber;
  const saved = {
    id: `rule-group-${number}`,
    name: `规则组${number}`,
    rules: cloneRules(rules),
  };
  const groups = [...(Array.isArray(currentGroups) ? currentGroups : state.groups), saved];
  writeState(storage, { nextNumber: number + 1, groups });
  return { saved, groups: loadRuleGroups(storage) };
}

export function deleteRuleGroup (storage, currentGroups, groupId) {
  const state = readState(storage);
  const groups = (Array.isArray(currentGroups) ? currentGroups : state.groups)
    .filter(group => group.id !== groupId);
  writeState(storage, { nextNumber: state.nextNumber, groups });
  return loadRuleGroups(storage);
}
