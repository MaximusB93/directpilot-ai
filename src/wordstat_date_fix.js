function normalizeMonthlyWordstatDate(value) {
  if (!value) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return value;
  return `${match[1]}-${match[2]}-01`;
}

document.addEventListener('submit', (event) => {
  const form = event.target?.closest?.('[data-wordstat-form]');
  if (!form) return;

  const period = form.querySelector('[name="period"]')?.value;
  if (period !== 'MONTHLY') return;

  const fromInput = form.querySelector('[name="fromDate"]');
  const toInput = form.querySelector('[name="toDate"]');
  if (fromInput) fromInput.value = normalizeMonthlyWordstatDate(fromInput.value);
  if (toInput) toInput.value = normalizeMonthlyWordstatDate(toInput.value);
}, true);
