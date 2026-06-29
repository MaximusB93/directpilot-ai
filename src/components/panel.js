import { escapeHtml } from '../core/html.js';

export function renderPanel({ title = '', subtitle = '', actions = '', children = '', className = '' } = {}) {
  const extraClass = className ? ` ${escapeHtml(className)}` : '';
  const subtitleHtml = subtitle ? `<p class="panelSubtitle">${escapeHtml(subtitle)}</p>` : '';
  const actionsHtml = actions ? `<div class="panelActions">${actions}</div>` : '';
  return `
    <section class="panel${extraClass}">
      <div class="panelHeader">
        <div>
          ${title ? `<h2>${escapeHtml(title)}</h2>` : ''}
          ${subtitleHtml}
        </div>
        ${actionsHtml}
      </div>
      ${children}
    </section>
  `;
}
