import {
  buildWordstatTotalPoints,
  buildWordstatTotalSummary,
  calculateWordstatPercentDelta,
  createDefaultWordstatForm,
  createInitialWordstatState,
  createPreviousWordstatPeriodRange,
  createSelectedWordstatRegionIds,
  createWordstatRequestBody,
  parseWordstatCustomRegions,
  parseWordstatPhrases,
  regionsSummary,
  WORDSTAT_LIMITS,
} from './wordstat-store.js';
import {
  fetchWordstatConnection,
  fetchWordstatDynamics,
} from './wordstat-service.js';

export {
  buildWordstatTotalPoints,
  buildWordstatTotalSummary,
  calculateWordstatPercentDelta,
  createDefaultWordstatForm,
  createInitialWordstatState,
  createPreviousWordstatPeriodRange,
  createSelectedWordstatRegionIds,
  createWordstatRequestBody,
  fetchWordstatConnection,
  fetchWordstatDynamics,
  parseWordstatCustomRegions,
  parseWordstatPhrases,
  regionsSummary,
  WORDSTAT_LIMITS,
};

export function createWordstatLegacyApi({
  state = createInitialWordstatState(),
  getSelectedClientId = () => null,
  regionById = new Map(),
  service = { fetchWordstatConnection, fetchWordstatDynamics },
} = {}) {
  return {
    state,
    limits: WORDSTAT_LIMITS,
    createDefaultForm: createDefaultWordstatForm,
    parsePhrases: parseWordstatPhrases,
    parseCustomRegions: parseWordstatCustomRegions,
    selectedRegionIds: () => createSelectedWordstatRegionIds(state.form),
    regionsSummary: (regionIds) => regionsSummary(regionIds, regionById),
    previousPeriodRange: () => createPreviousWordstatPeriodRange(state.form),
    percentDelta: calculateWordstatPercentDelta,
    buildTotalPoints: buildWordstatTotalPoints,
    buildTotalSummary: buildWordstatTotalSummary,
    createRequestBody: (overrides = {}) => createWordstatRequestBody(state.form, getSelectedClientId(), overrides),
    loadConnection: () => service.fetchWordstatConnection(),
    loadDynamics: (overrides = {}) => service.fetchWordstatDynamics(
      createWordstatRequestBody(state.form, getSelectedClientId(), overrides),
    ),
  };
}
