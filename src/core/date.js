const RU_MONTHS_GENITIVE = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

/**
 * Parses a date-only or full ISO timestamp into {year, month, day}.
 * Reads the leading `YYYY-MM-DD` directly, so a timestamp keeps the day the
 * backend meant regardless of the viewer's timezone.
 */
function parseIsoDateParts(value) {
  const match = String(value ?? '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  const [, year, month, day] = match;
  const monthIndex = Number(month) - 1;
  if (monthIndex < 0 || monthIndex > 11) return null;
  return { year: Number(year), monthIndex, day: Number(day) };
}

/**
 * «9 июня — 8 июля 2026» — a period a human can read.
 * The year is printed once when both ends share it. Returns an empty string
 * when the input cannot be parsed, so callers never print a raw timestamp.
 */
export function formatDateRange(from, to) {
  const start = parseIsoDateParts(from);
  const end = parseIsoDateParts(to);
  if (!start && !end) return '';
  if (!start || !end) {
    const single = start || end;
    return `${single.day} ${RU_MONTHS_GENITIVE[single.monthIndex]} ${single.year}`;
  }
  const sameYear = start.year === end.year;
  const startText = sameYear
    ? `${start.day} ${RU_MONTHS_GENITIVE[start.monthIndex]}`
    : `${start.day} ${RU_MONTHS_GENITIVE[start.monthIndex]} ${start.year}`;
  const endText = `${end.day} ${RU_MONTHS_GENITIVE[end.monthIndex]} ${end.year}`;
  if (sameYear && start.monthIndex === end.monthIndex && start.day === end.day) {
    return endText;
  }
  return `${startText} — ${endText}`;
}

export function normalizeMonthlyFromDate(value) {
  if (!value) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return `${match[1]}-${match[2]}-01`;
}

export function normalizeMonthlyToDate(value) {
  if (!value) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const lastDay = new Date(year, month, 0).getDate();
  return `${match[1]}-${match[2]}-${String(lastDay).padStart(2, '0')}`;
}
