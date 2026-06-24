const WORDSTAT_DEFAULT_TO_DATE_APPLIED_ATTR = 'data-wordstat-default-to-date-applied';

function toDateInputValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function lastDayOfMonth(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0);
}

function defaultWordstatToDate() {
  const today = new Date();
  const target = new Date(today.getFullYear(), today.getMonth() + 3, 1);
  return lastDayOfMonth(target.getFullYear(), target.getMonth());
}

function normalizeMonthlyWordstatFromDate(value) {
  if (!value) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return `${match[1]}-${match[2]}-01`;
}

function normalizeMonthlyWordstatToDate(value) {
  if (!value) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const lastDay = new Date(year, month, 0).getDate();
  return `${match[1]}-${match[2]}-${String(lastDay).padStart(2, '0')}`;
}

function applyWordstatMonthlyDateDefaults(root = document) {
  const form = root.querySelector?.('[data-wordstat-form]') || document.querySelector('[data-wordstat-form]');
  if (!form || form.hasAttribute(WORDSTAT_DEFAULT_TO_DATE_APPLIED_ATTR)) return;

  const period = form.querySelector('[name="period"]')?.value;
  if (period !== 'MONTHLY') return;

  const fromInput = form.querySelector('[name="fromDate"]');
  const toInput = form.querySelector('[name="toDate"]');
  if (fromInput) fromInput.value = normalizeMonthlyWordstatFromDate(fromInput.value);
  if (toInput) toInput.value = toDateInputValue(defaultWordstatToDate());
  form.setAttribute(WORDSTAT_DEFAULT_TO_DATE_APPLIED_ATTR, 'true');
}

document.addEventListener('submit', (event) => {
  const form = event.target?.closest?.('[data-wordstat-form]');
  if (!form) return;

  const period = form.querySelector('[name="period"]')?.value;
  if (period !== 'MONTHLY') return;

  const fromInput = form.querySelector('[name="fromDate"]');
  const toInput = form.querySelector('[name="toDate"]');
  if (fromInput) fromInput.value = normalizeMonthlyWordstatFromDate(fromInput.value);
  if (toInput) toInput.value = normalizeMonthlyWordstatToDate(toInput.value);
}, true);

const observer = new MutationObserver(() => applyWordstatMonthlyDateDefaults());
observer.observe(document.body, { childList: true, subtree: true });
applyWordstatMonthlyDateDefaults();
