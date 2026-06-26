const RU_NUMBER_FORMAT = new Intl.NumberFormat('ru-RU');
const RU_MONEY_FORMAT = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
});

export function formatNumber(value, fallback = '0') {
  const number = Number(value || 0);
  return Number.isFinite(number) ? RU_NUMBER_FORMAT.format(number) : fallback;
}

export function formatMoney(value, fallback = '—') {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? RU_MONEY_FORMAT.format(number) : fallback;
}

export function formatPercent(value, fallback = '—', digits = 2) {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return `${number > 0 ? '+' : ''}${number.toFixed(digits)}%`;
}

export function formatPlainPercent(value, fallback = '—', digits = 1) {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return `${number.toFixed(digits)}%`;
}

export function formatDate(value, fallback = '—') {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return date.toLocaleDateString('ru-RU');
}

export function formatFallback(value, fallback = '—') {
  const text = String(value ?? '').trim();
  return text || fallback;
}
