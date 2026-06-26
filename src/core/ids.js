export function createClientId(prefix = 'client') {
  const suffix = Date.now().toString(36);
  return `${prefix}_${suffix}`;
}

export function normalizeId(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9а-яё_-]+/gi, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

export function hasSameId(left, right) {
  return String(left || '') === String(right || '');
}
