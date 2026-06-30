export const WORDSTAT_DEFAULT_PHRASES = 'купить диван\nдиван кровать\nугловой диван';

export const WORDSTAT_ALLOWED_PERIODS = Object.freeze(['DAILY', 'WEEKLY', 'MONTHLY']);
export const WORDSTAT_ALLOWED_DEVICES = Object.freeze(['DEVICE_ALL', 'DEVICE_DESKTOP', 'DEVICE_PHONE', 'DEVICE_TABLET']);

export const WORDSTAT_LIMITS = Object.freeze({
  maxPhrasesPerBatch: 50,
  maxPhraseLength: 400,
  maxRegions: 100,
  maxDevices: 3,
});

export function startOfDay(date = new Date()) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addMonths(date, months) {
  const result = new Date(date);
  const day = result.getDate();
  result.setMonth(result.getMonth() + months, 1);
  const maxDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
  result.setDate(Math.min(day, maxDay));
  return result;
}

export function addDays(date, days) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

export function parseInputDate(value) {
  const [year, month, day] = String(value || '').split('-').map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

export function toInputDate(date) {
  const safeDate = date instanceof Date && !Number.isNaN(date.getTime()) ? date : new Date();
  const year = safeDate.getFullYear();
  const month = String(safeDate.getMonth() + 1).padStart(2, '0');
  const day = String(safeDate.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function normalizeWordstatPeriod(period = 'WEEKLY') {
  return WORDSTAT_ALLOWED_PERIODS.includes(period) ? period : 'WEEKLY';
}

export function normalizeWordstatDevice(device = 'DEVICE_ALL') {
  return WORDSTAT_ALLOWED_DEVICES.includes(device) ? device : 'DEVICE_ALL';
}

export function createDefaultWordstatForm({ now = new Date() } = {}) {
  const today = startOfDay(now);
  const from = addMonths(today, -3);
  return {
    phrases: WORDSTAT_DEFAULT_PHRASES,
    period: 'WEEKLY',
    fromDate: toInputDate(from),
    toDate: toInputDate(today),
    compareFromDate: '',
    compareToDate: '',
    regions: [],
    customRegions: '',
    devices: 'DEVICE_ALL',
    forceRefresh: false,
  };
}

export function createInitialWordstatState({ now = new Date() } = {}) {
  return {
    mounted: false,
    active: false,
    loading: false,
    compareLoading: false,
    comparePanelOpen: false,
    regionModalOpen: false,
    regionDraftRegions: [],
    regionDraftCustom: '',
    expandedRegions: new Set(['225', '1', '10174', '1095']),
    status: '',
    error: '',
    connection: null,
    result: null,
    comparison: null,
    comparisonRange: null,
    form: createDefaultWordstatForm({ now }),
  };
}

export function parseWordstatPhrases(value) {
  return String(value || '')
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseWordstatCustomRegions(value) {
  return String(value || '')
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function createSelectedWordstatRegionIds(form = {}) {
  return [...new Set([...(form.regions || []), ...parseWordstatCustomRegions(form.customRegions)])];
}

export function createWordstatRequestBody(form = {}, clientId = null, overrides = {}) {
  const fromDate = overrides.fromDate ?? form.fromDate;
  const toDate = overrides.toDate ?? form.toDate;
  const rawDevices = overrides.devices ?? form.devices ?? 'DEVICE_ALL';
  const devices = Array.isArray(rawDevices) ? rawDevices : [rawDevices];

  return {
    phrases: parseWordstatPhrases(overrides.phrases ?? form.phrases),
    period: normalizeWordstatPeriod(overrides.period ?? form.period),
    fromDate,
    toDate,
    regions: overrides.regions ?? createSelectedWordstatRegionIds(form),
    devices: devices.map(normalizeWordstatDevice),
    clientId: clientId || null,
    forceRefresh: Boolean(overrides.forceRefresh ?? form.forceRefresh),
  };
}

export function createPreviousWordstatPeriodRange(form = {}) {
  const from = parseInputDate(form.fromDate);
  const to = parseInputDate(form.toDate);
  if (!from || !to) return null;
  const days = Math.max(1, Math.round((to - from) / 86400000) + 1);
  const prevTo = addDays(from, -1);
  const prevFrom = addDays(prevTo, -(days - 1));
  return { fromDate: toInputDate(prevFrom), toDate: toInputDate(prevTo) };
}

export function calculateWordstatPercentDelta(current, previous) {
  if (previous === null || previous === undefined || Number(previous) === 0) return null;
  return Math.round(((Number(current || 0) - Number(previous)) / Number(previous)) * 10000) / 100;
}

export function buildWordstatTotalPoints(result = {}) {
  const byDate = new Map();
  for (const series of result.series || []) {
    if (series.error) continue;
    for (const point of series.points || []) {
      const existing = byDate.get(point.date) || { date: point.date, count: 0, share: null };
      existing.count += Number(point.count || 0);
      byDate.set(point.date, existing);
    }
  }

  const ordered = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  const first = ordered.find((point) => point.count)?.count || 0;
  let previous = null;

  return ordered.map((point) => {
    const enriched = {
      ...point,
      mom: calculateWordstatPercentDelta(point.count, previous),
      yoy: null,
      index: first ? Math.round((point.count / first) * 10000) / 100 : null,
    };
    previous = point.count;
    return enriched;
  });
}

export function buildWordstatTotalSummary(result = {}) {
  const points = buildWordstatTotalPoints(result);
  const total = points.reduce((sum, point) => sum + Number(point.count || 0), 0);
  const firstCount = points[0]?.count || 0;
  const lastCount = points.at(-1)?.count || 0;
  return {
    points: points.length,
    total,
    firstCount,
    lastCount,
    growthPercent: calculateWordstatPercentDelta(lastCount, firstCount),
  };
}

export function regionsSummary(regionIds = [], regionById = new Map()) {
  if (!regionIds?.length) return 'Все регионы';
  const labels = regionIds.map((id) => {
    const region = regionById.get(String(id));
    return region ? `${region.name} (${region.id})` : String(id);
  });
  return labels.length > 4 ? `${labels.slice(0, 4).join(', ')} и ещё ${labels.length - 4}` : labels.join(', ');
}
