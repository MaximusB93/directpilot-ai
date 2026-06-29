import { escapeHtml } from '../core/html.js';

const STATUS_BADGE_TONES = new Set(['neutral', 'success', 'warning', 'danger', 'info']);

export function normalizeStatusBadgeTone(tone = 'neutral') {
  return STATUS_BADGE_TONES.has(tone) ? tone : 'neutral';
}

export function renderStatusBadge({ label, tone = 'neutral', title = '' } = {}) {
  const safeTone = normalizeStatusBadgeTone(tone);
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
  return `<span class="statusBadge statusBadge--${safeTone}"${titleAttr}>${escapeHtml(label || '')}</span>`;
}
