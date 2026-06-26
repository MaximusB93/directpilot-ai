import { normalizeMonthlyFromDate, normalizeMonthlyToDate } from './core/date.js';

document.addEventListener('submit', (event) => {
  const form = event.target?.closest?.('[data-wordstat-form]');
  if (!form) return;

  const period = form.querySelector('[name="period"]')?.value;
  if (period !== 'MONTHLY') return;

  const fromInput = form.querySelector('[name="fromDate"]');
  const toInput = form.querySelector('[name="toDate"]');
  if (fromInput) fromInput.value = normalizeMonthlyFromDate(fromInput.value);
  if (toInput) toInput.value = normalizeMonthlyToDate(toInput.value);
}, true);
