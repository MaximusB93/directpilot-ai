const WORDSTAT_AI_QUICK_QUESTIONS = [
  'Сделай краткий вывод по спросу: что растёт, что падает и что важно проверить?',
  'Какие фразы лучше использовать для рекламы, а какие для SEO?',
  'Есть ли сезонность или аномалии в этих данных?',
  'Сравни текущий период с периодом сравнения и дай выводы.',
];

const WORDSTAT_PAYLOAD_KEY = 'directpilot_wordstat_last_payload';
const WORDSTAT_NEXT_PAYLOAD_KIND_KEY = 'directpilot_wordstat_next_payload_kind';
const CUSTOM_MODEL_VALUE = '__custom_openrouter_model__';

const wordstatAiState = {
  messages: [],
  loading: false,
};

function resolveApiBase() {
  const custom = window.localStorage.getItem('directpilot_api_base')?.trim();
  if (custom) return custom.replace(/\/$/, '');
  const { hostname, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') return 'http://localhost:8000/api/v1';
  if (hostname === 'maximusb93.github.io') return 'https://directpilot-ai.vercel.app/api/v1';
  return `${origin}/api/v1`;
}

function getSessionToken() {
  return window.localStorage.getItem('directpilot_session') || '';
}

function getCurrentEmail() {
  return (window.localStorage.getItem('directpilot_email') || '').trim().toLowerCase();
}

function scopedStorageKey(key) {
  const email = getCurrentEmail();
  return email ? `${key}_${email}` : key;
}

function getSelectedAiSettings() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(scopedStorageKey('directpilot_ai_model_settings')) || '{}');
    const selectedModel = String(saved.selectedModel || '').trim();
    const customModel = String(saved.customModel || '').trim();
    const model = selectedModel === CUSTOM_MODEL_VALUE ? customModel : selectedModel;
    return {
      model: model || null,
      ai_preset: saved.selectedPreset ? String(saved.selectedPreset) : null,
      max_tokens: 2500,
      compactContext: saved.compactContext,
      toolResultsMode: saved.toolResultsMode,
      chatHistoryLimit: saved.chatHistoryLimit,
      searchQueryLimit: saved.searchQueryLimit,
    };
  } catch {
    return { model: null, ai_preset: null, max_tokens: 2500 };
  }
}

async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getSessionToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${resolveApiBase()}${path}`, { ...options, headers });
  if (response.status === 401) {
    localStorage.removeItem('directpilot_session');
    localStorage.removeItem('directpilot_email');
    window.location.href = 'login.html';
    throw new Error('Authentication required');
  }
  return response;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function readStoredWordstatPayload() {
  try {
    const raw = sessionStorage.getItem(WORDSTAT_PAYLOAD_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStoredWordstatPayload(next) {
  sessionStorage.setItem(WORDSTAT_PAYLOAD_KEY, JSON.stringify(next));
  window.dispatchEvent(new CustomEvent('directpilot:wordstat-payload-updated', { detail: next }));
}

function storeWordstatApiPayload(payload, kind = 'current') {
  if (!payload || typeof payload !== 'object') return;
  const previous = readStoredWordstatPayload() || {};
  const next = kind === 'comparison'
    ? { ...previous, comparison: payload }
    : { current: payload, comparison: null };
  writeStoredWordstatPayload(next);
}

function patchFetchForWordstatPayload() {
  if (window.fetch.__wordstatPayloadPatched) return;
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    try {
      const url = String(args[0] instanceof Request ? args[0].url : args[0] || '');
      if (url.includes('/wordstat/dynamics/batch') && response.ok) {
        const clone = response.clone();
        const payload = await clone.json();
        const kind = sessionStorage.getItem(WORDSTAT_NEXT_PAYLOAD_KIND_KEY) || 'current';
        sessionStorage.removeItem(WORDSTAT_NEXT_PAYLOAD_KIND_KEY);
        storeWordstatApiPayload(payload, kind === 'comparison' ? 'comparison' : 'current');
      }
    } catch {
      // Do not break the original request if diagnostics storage fails.
    }
    return response;
  };
  window.fetch.__wordstatPayloadPatched = true;
}

function getLatestWordstatJson() {
  return readStoredWordstatPayload();
}

function compactVisibleWordstatTables() {
  const details = [...document.querySelectorAll('.aiToolTrace')].slice(0, 12);
  return details.map((item) => {
    const title = item.querySelector('summary')?.textContent?.trim() || '';
    const rows = [...item.querySelectorAll('tbody tr')].slice(0, 60).map((row) => [...row.children].map((cell) => cell.textContent.trim()));
    return { title, rows };
  });
}

function collectWordstatContext() {
  const payload = getLatestWordstatJson();
  const current = payload?.current || null;
  const comparison = payload?.comparison || null;
  const summaryCards = [...document.querySelectorAll('.clientSourcePanel div')].map((item) => item.textContent.trim()).filter(Boolean);
  const phraseRows = [...document.querySelectorAll('.tableWrap table tbody tr')].slice(0, 120).map((row) => [...row.children].map((cell) => cell.textContent.trim()));
  return {
    current: current || { visibleSummaryCards: summaryCards, visibleRows: phraseRows, visibleDetails: compactVisibleWordstatTables() },
    comparison,
    visibleSummaryCards: summaryCards,
    visibleRows: phraseRows,
    visibleDetails: compactVisibleWordstatTables(),
    hasStoredPayload: Boolean(current),
  };
}

function currentModelLabel() {
  const settings = getSelectedAiSettings();
  return settings.model || 'модель из backend по умолчанию';
}

function renderWordstatAiChat() {
  const resultPanel = [...document.querySelectorAll('.panel')].find((panel) => panel.textContent.includes('Итоги batch-запроса'));
  if (!resultPanel || document.querySelector('[data-wordstat-ai-chat]')) return;

  const section = document.createElement('section');
  section.className = 'panel';
  section.dataset.wordstatAiChat = 'true';
  section.innerHTML = `
    <div class="panelHeader">
      <div>
        <h3>AI-анализ Wordstat</h3>
        <p>ИИ берёт последний полный Wordstat payload из batch-запроса, а не гадает по пустой странице. Используемая модель: <strong>${escapeHtml(currentModelLabel())}</strong>.</p>
      </div>
      <span class="aiStatusBadge ready">AI chat</span>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;">
      ${WORDSTAT_AI_QUICK_QUESTIONS.map((question) => `<button class="secondaryButton" type="button" data-wordstat-ai-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`).join('')}
    </div>
    <div data-wordstat-ai-messages style="display:grid;gap:10px;margin-bottom:12px;">${renderMessages()}</div>
    <form data-wordstat-ai-form class="clientConnectForm">
      <label class="authField" style="grid-column:1 / -1;">
        <span>Вопрос к ИИ</span>
        <textarea name="question" rows="3" placeholder="Например: какие фразы растут быстрее и что это значит для рекламы?"></textarea>
      </label>
      <div class="heroActions" style="grid-column:1 / -1;">
        <button class="approveButton" type="submit" ${wordstatAiState.loading ? 'disabled' : ''}>${wordstatAiState.loading ? 'Анализируем...' : 'Спросить ИИ'}</button>
        <button class="secondaryButton" type="button" data-wordstat-ai-summary>Сделать авто-анализ</button>
      </div>
    </form>
  `;
  resultPanel.insertAdjacentElement('afterend', section);
}

function renderMessages() {
  if (!wordstatAiState.messages.length) {
    const payload = getLatestWordstatJson();
    const status = payload?.current?.series?.length
      ? `Контекст готов: ${payload.current.series.length} фраз.`
      : 'Контекст ещё не сохранён. Получи динамику Wordstat заново, чтобы ИИ увидел полный JSON.';
    return `<div class="authStatus integrationStatus">${escapeHtml(status)}</div>`;
  }
  return wordstatAiState.messages.map((message) => `
    <article style="border:1px solid #d8e0ec;border-radius:16px;padding:12px;background:${message.role === 'user' ? '#f8fafc' : '#fff'};">
      <strong>${message.role === 'user' ? 'Вы' : 'AI'}${message.model ? ` · ${escapeHtml(message.model)}` : ''}</strong>
      <div style="white-space:pre-wrap;margin-top:6px;">${escapeHtml(message.content)}</div>
    </article>
  `).join('');
}

function rerenderMessages() {
  const box = document.querySelector('[data-wordstat-ai-messages]');
  if (box) box.innerHTML = renderMessages();
  const submit = document.querySelector('[data-wordstat-ai-form] button[type="submit"]');
  if (submit) {
    submit.textContent = wordstatAiState.loading ? 'Анализируем...' : 'Спросить ИИ';
    submit.disabled = wordstatAiState.loading;
  }
}

async function askWordstatAi(question) {
  const context = collectWordstatContext();
  const current = context.current;
  const hasData = Boolean(current?.series?.length || context.visibleRows.length);
  if (!hasData) {
    wordstatAiState.messages.push({ role: 'assistant', content: 'Сначала получи динамику Wordstat заново. Сейчас в контексте нет ни series, ни видимых строк таблицы.' });
    rerenderMessages();
    return;
  }
  wordstatAiState.messages.push({ role: 'user', content: question });
  wordstatAiState.loading = true;
  rerenderMessages();

  const aiSettings = getSelectedAiSettings();
  try {
    const response = await apiFetch('/wordstat/ai-chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        wordstat: current || context,
        comparison: context.comparison,
        history: wordstatAiState.messages.slice(-6).map((item) => ({ role: item.role, content: item.content })),
        model: aiSettings.model,
        ai_preset: aiSettings.ai_preset || 'balanced',
        max_tokens: aiSettings.max_tokens || 2500,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'AI не вернул ответ');
    wordstatAiState.messages.push({ role: 'assistant', content: payload.answer || 'Пустой ответ от AI.', model: payload.model || aiSettings.model || '' });
  } catch (error) {
    if (error.message === 'Authentication required') return;
    wordstatAiState.messages.push({ role: 'assistant', content: `Ошибка AI-анализа: ${error.message}` });
  } finally {
    wordstatAiState.loading = false;
    rerenderMessages();
  }
}

function patchClipboardForWordstatPayload() {
  if (!navigator.clipboard?.writeText || navigator.clipboard.writeText.__wordstatPatched) return;
  const originalWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
  navigator.clipboard.writeText = async (text) => {
    try {
      const parsed = JSON.parse(text);
      if (parsed?.current || parsed?.series || parsed?.summary) {
        writeStoredWordstatPayload(parsed?.current ? parsed : { current: parsed, comparison: null });
      }
    } catch {
      // ignore non-json clipboard writes
    }
    return originalWriteText(text);
  };
  navigator.clipboard.writeText.__wordstatPatched = true;
}

const observer = new MutationObserver(() => renderWordstatAiChat());
observer.observe(document.body, { childList: true, subtree: true });
patchFetchForWordstatPayload();
patchClipboardForWordstatPayload();
renderWordstatAiChat();

document.addEventListener('submit', async (event) => {
  if (event.target.closest('[data-wordstat-form]')) {
    sessionStorage.setItem(WORDSTAT_NEXT_PAYLOAD_KIND_KEY, 'current');
  }
  const form = event.target.closest('[data-wordstat-ai-form]');
  if (!form) return;
  event.preventDefault();
  const question = String(new FormData(form).get('question') || '').trim();
  if (!question) return;
  form.reset();
  await askWordstatAi(question);
}, true);

document.addEventListener('click', async (event) => {
  if (event.target.closest('[data-wordstat-run-compare]')) {
    sessionStorage.setItem(WORDSTAT_NEXT_PAYLOAD_KIND_KEY, 'comparison');
  }
  const quick = event.target.closest('[data-wordstat-ai-question]');
  if (quick) {
    await askWordstatAi(quick.dataset.wordstatAiQuestion || quick.textContent.trim());
    return;
  }
  if (event.target.closest('[data-wordstat-ai-summary]')) {
    await askWordstatAi('Проанализируй текущие данные Wordstat: дай вывод по спросу, трендам, сезонности, сильным/слабым фразам, ограничениям данных и практическим действиям для рекламы и SEO.');
  }
}, true);

window.addEventListener('directpilot:wordstat-payload-updated', () => rerenderMessages());
