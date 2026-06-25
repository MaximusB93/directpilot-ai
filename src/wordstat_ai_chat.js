const WORDSTAT_AI_QUICK_QUESTIONS = [
  'Сделай краткий вывод по спросу: что растёт, что падает и что важно проверить?',
  'Какие фразы лучше использовать для рекламы, а какие для SEO?',
  'Есть ли сезонность или аномалии в этих данных?',
  'Сравни текущий период с периодом сравнения и дай выводы.',
];

const wordstatAiState = {
  messages: [],
  loading: false,
  lastAnswer: '',
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

function getLatestWordstatJsonFromCopyButton() {
  // The primary module keeps Wordstat state in module scope. This patch cannot read it directly,
  // so we mirror the Copy JSON action by monkey-patching clipboard writes below.
  try {
    const raw = sessionStorage.getItem('directpilot_wordstat_last_payload');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function compactVisibleWordstatTables() {
  const details = [...document.querySelectorAll('.aiToolTrace')].slice(0, 12);
  return details.map((item) => {
    const title = item.querySelector('summary')?.textContent?.trim() || '';
    const rows = [...item.querySelectorAll('tbody tr')].slice(0, 40).map((row) => [...row.children].map((cell) => cell.textContent.trim()));
    return { title, rows };
  });
}

function collectWordstatContext() {
  const payload = getLatestWordstatJsonFromCopyButton();
  const current = payload?.current || payload || null;
  const comparison = payload?.comparison || null;
  const summaryCards = [...document.querySelectorAll('.clientSourcePanel div')].map((item) => item.textContent.trim()).filter(Boolean);
  const phraseRows = [...document.querySelectorAll('.tableWrap table tbody tr')].slice(0, 80).map((row) => [...row.children].map((cell) => cell.textContent.trim()));
  return {
    current: current || { visibleSummaryCards: summaryCards, visibleRows: phraseRows, visibleDetails: compactVisibleWordstatTables() },
    comparison,
    visibleSummaryCards: summaryCards,
    visibleRows: phraseRows,
    visibleDetails: compactVisibleWordstatTables(),
  };
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
        <p>Задай вопрос по последней выгрузке. ИИ возьмёт текущие данные Wordstat, таблицы, суммы и сравнение, если оно загружено.</p>
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
    return '<div class="authStatus integrationStatus">ИИ пока ничего не анализировал. Нажми авто-анализ или задай вопрос по данным.</div>';
  }
  return wordstatAiState.messages.map((message) => `
    <article style="border:1px solid #d8e0ec;border-radius:16px;padding:12px;background:${message.role === 'user' ? '#f8fafc' : '#fff'};">
      <strong>${message.role === 'user' ? 'Вы' : 'AI'}</strong>
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
  if (!current && !context.visibleRows.length) {
    wordstatAiState.messages.push({ role: 'assistant', content: 'Сначала получи динамику Wordstat, иначе анализировать нечего. Даже ИИ не должен гадать на пустой таблице.' });
    rerenderMessages();
    return;
  }
  wordstatAiState.messages.push({ role: 'user', content: question });
  wordstatAiState.loading = true;
  rerenderMessages();

  try {
    const response = await apiFetch('/wordstat/ai-chat', {
      method: 'POST',
      body: JSON.stringify({
        question,
        wordstat: current || context,
        comparison: context.comparison,
        history: wordstatAiState.messages.slice(-6).map((item) => ({ role: item.role, content: item.content })),
        ai_preset: 'economy',
        max_tokens: 2500,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'AI не вернул ответ');
    wordstatAiState.messages.push({ role: 'assistant', content: payload.answer || 'Пустой ответ от AI.' });
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
        sessionStorage.setItem('directpilot_wordstat_last_payload', JSON.stringify(parsed));
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
patchClipboardForWordstatPayload();
renderWordstatAiChat();

document.addEventListener('submit', async (event) => {
  const form = event.target.closest('[data-wordstat-ai-form]');
  if (!form) return;
  event.preventDefault();
  const question = String(new FormData(form).get('question') || '').trim();
  if (!question) return;
  form.reset();
  await askWordstatAi(question);
});

document.addEventListener('click', async (event) => {
  const quick = event.target.closest('[data-wordstat-ai-question]');
  if (quick) {
    await askWordstatAi(quick.dataset.wordstatAiQuestion || quick.textContent.trim());
    return;
  }
  if (event.target.closest('[data-wordstat-ai-summary]')) {
    await askWordstatAi('Проанализируй текущие данные Wordstat: дай вывод по спросу, трендам, сезонности, сильным/слабым фразам, ограничениям данных и практическим действиям для рекламы и SEO.');
  }
});
