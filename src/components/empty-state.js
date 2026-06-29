import { escapeHtml } from '../core/html.js';

export function renderEmptyState({ title = 'Нет данных', description = '', action = '' } = {}) {
  const descriptionHtml = description ? `<p>${escapeHtml(description)}</p>` : '';
  const actionHtml = action ? `<div class="emptyStateAction">${action}</div>` : '';
  return `
    <div class="emptyState">
      <strong>${escapeHtml(title)}</strong>
      ${descriptionHtml}
      ${actionHtml}
    </div>
  `;
}
