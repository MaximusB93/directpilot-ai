import { apiFetch, escapeHtml } from './core/api.js';
import { getCurrentEmail, scopedStorageKey } from './core/storage.js';

const AUTOFILL_FIELDS = [
  'brandName',
  'businessNiche',
  'productSummary',
  'targetAudience',
  'geography',
  'seasonality',
  'mainOffers',
  'conversionActions',
  'averageOrderValue',
  'leadValueNotes',
  'businessConstraints',
  'negativeTopics',
  'landingPageNotes',
  'competitorNotes',
  'aiSummary',
  'sourceNotes',
];

function getSelectedClientId() {
  const selectedFromDom = document.querySelector('[data-client-select]')?.value || '';
  if (selectedFromDom) return selectedFromDom;
  return window.localStorage.getItem(scopedStorageKey('directpilot_selected_client_id', getCurrentEmail())) || '';
}

function parseUrls(value) {
  return String(value || '')
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 5);
}

function renderSourceNote(source) {
  const titleOrError = source.error || source.title || source.contentSample || '—';
  const method = source.extractionMethod || (source.error ? 'error' : 'unknown');
  const textInfo = `${source.textLength || 0} / html ${source.contentLength || 0}`;
  return `
    <tr>
      <td>${escapeHtml(source.finalUrl || source.url || '—')}</td>
      <td>${escapeHtml(String(source.statusCode || '—'))}</td>
      <td>${escapeHtml(method)}</td>
      <td>${escapeHtml(textInfo)}</td>
      <td>${escapeHtml(titleOrError)}</td>
    </tr>
  `;
}

function renderSources(payload) {
  const warnings = payload?.warnings || [];
  const sources = payload?.sources || [];
  return `
    ${warnings.length ? `<div class="authStatus integrationStatus"><strong>Проверьте вручную</strong>${warnings.map((item) => `<p>${escapeHtml(item)}</p>`).join('')}</div>` : ''}
    ${sources.length ? `
      <div class="tableWrap businessAutofillSources">
        <table>
          <thead><tr><th>URL</th><th>Статус</th><th>Метод</th><th>Текст / HTML</th><th>Заголовок / ошибка / sample</th></tr></thead>
          <tbody>${sources.map(renderSourceNote).join('')}</tbody>
        </table>
      </div>
    ` : ''}
  `;
}

function applyDraftToForm(draft, overwrite) {
  const form = document.querySelector('[data-business-context-form]');
  if (!form || !draft) return 0;
  let applied = 0;
  AUTOFILL_FIELDS.forEach((field) => {
    const value = String(draft[field] || '').trim();
    if (!value) return;
    const input = form.querySelector(`[name="${field}"]`);
    if (!input) return;
    if (!overwrite && String(input.value || '').trim()) return;
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    applied += 1;
  });
  return applied;
}

function ensureBusinessAutofillPanel() {
  const form = document.querySelector('[data-business-context-form]');
  if (!form || document.querySelector('[data-business-autofill-panel]')) return;
  const panel = document.createElement('section');
  panel.className = 'panel businessAutofillPanel';
  panel.dataset.businessAutofillPanel = 'true';
  panel.innerHTML = `
    <div class="panelHeader">
      <div>
        <span class="eyebrow">AI-автозаполнение</span>
        <h3>Заполнить контекст по сайту</h3>
        <p>Вставьте до 5 ссылок. DirectPilot прочитает HTML-страницы, соберёт факты и заполнит форму как черновик. Сохранение остаётся вручную.</p>
      </div>
      <span class="aiStatusBadge pending">review first</span>
    </div>
    <label class="authField">
      <span>Ссылки на сайт или посадочные страницы</span>
      <textarea rows="3" data-business-autofill-urls placeholder="https://site.ru/&#10;https://site.ru/offers"></textarea>
    </label>
    <label class="businessAutofillCheckbox">
      <input type="checkbox" data-business-autofill-overwrite />
      <span>Перезаписать уже заполненные поля</span>
    </label>
    <div class="heroActions">
      <button class="approveButton" type="button" data-business-autofill-run>Автозаполнить из сайта</button>
      <button class="secondaryButton" type="button" data-business-autofill-clear>Очистить ссылки</button>
    </div>
    <div class="authStatus integrationStatus" data-business-autofill-status>AI заполнит форму, но не сохранит её. После проверки нажмите «Сохранить контекст».</div>
    <div data-business-autofill-result></div>
  `;
  form.parentElement?.insertBefore(panel, form);
}

async function runBusinessContextAutofill(button) {
  const panel = button.closest('[data-business-autofill-panel]');
  const statusBox = panel?.querySelector('[data-business-autofill-status]');
  const resultBox = panel?.querySelector('[data-business-autofill-result]');
  const urlsInput = panel?.querySelector('[data-business-autofill-urls]');
  const overwrite = Boolean(panel?.querySelector('[data-business-autofill-overwrite]')?.checked);
  const clientId = getSelectedClientId();
  const urls = parseUrls(urlsInput?.value || '');
  if (!clientId) {
    if (statusBox) statusBox.textContent = 'Сначала выберите клиента.';
    return;
  }
  if (!urls.length) {
    if (statusBox) statusBox.textContent = 'Добавьте хотя бы одну ссылку.';
    return;
  }
  button.disabled = true;
  button.textContent = 'Читаем сайт...';
  if (statusBox) statusBox.textContent = 'Получаем страницы и просим AI собрать бизнес-контекст...';
  if (resultBox) resultBox.innerHTML = '';
  try {
    const response = await apiFetch(`/clients/${encodeURIComponent(clientId)}/business-context/autofill`, {
      method: 'POST',
      body: JSON.stringify({ urls }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось автозаполнить контекст');
    const applied = applyDraftToForm(payload.draft, overwrite);
    if (statusBox) statusBox.textContent = `Черновик применён к форме: заполнено полей ${applied}. Проверьте текст и нажмите «Сохранить контекст».`;
    if (resultBox) resultBox.innerHTML = renderSources(payload);
  } catch (error) {
    if (statusBox) statusBox.textContent = `Ошибка автозаполнения: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = 'Автозаполнить из сайта';
  }
}

document.addEventListener('click', (event) => {
  const runButton = event.target.closest('[data-business-autofill-run]');
  if (runButton) {
    runBusinessContextAutofill(runButton);
    return;
  }
  const clearButton = event.target.closest('[data-business-autofill-clear]');
  if (clearButton) {
    const panel = clearButton.closest('[data-business-autofill-panel]');
    const textarea = panel?.querySelector('[data-business-autofill-urls]');
    if (textarea) textarea.value = '';
  }
});

const observer = new MutationObserver(() => ensureBusinessAutofillPanel());
observer.observe(document.body, { childList: true, subtree: true });
ensureBusinessAutofillPanel();
