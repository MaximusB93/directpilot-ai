const CUSTOM_MODEL_VALUE = '__custom_openrouter_model__';

function getCurrentEmail() {
  return (window.localStorage.getItem('directpilot_email') || '').trim().toLowerCase();
}

function scopedStorageKey(key) {
  const email = getCurrentEmail();
  return email ? `${key}_${email}` : key;
}

function selectedWordstatAiModel() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(scopedStorageKey('directpilot_ai_model_settings')) || '{}');
    const selected = String(saved.selectedModel || '').trim();
    const custom = String(saved.customModel || '').trim();
    return selected === CUSTOM_MODEL_VALUE ? custom : selected || 'backend-default';
  } catch {
    return 'backend-default';
  }
}

function isModelQuestion(text) {
  const value = String(text || '').toLowerCase();
  return value.includes('модель') || value.includes('model');
}

function appendWordstatAiMessage(role, content, model = '') {
  const box = document.querySelector('[data-wordstat-ai-messages]');
  if (!box) return;
  const empty = box.querySelector('.authStatus');
  if (empty) empty.remove();
  const article = document.createElement('article');
  article.style.cssText = `border:1px solid #d8e0ec;border-radius:16px;padding:12px;background:${role === 'user' ? '#f8fafc' : '#fff'};`;
  article.innerHTML = `
    <strong>${role === 'user' ? 'Вы' : 'AI'}${model ? ` · ${escapeHtml(model)}` : ''}</strong>
    <div style="white-space:pre-wrap;margin-top:6px;">${escapeHtml(content)}</div>
  `;
  box.appendChild(article);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

document.addEventListener('submit', (event) => {
  const form = event.target.closest('[data-wordstat-ai-form]');
  if (!form) return;
  const question = String(new FormData(form).get('question') || '').trim();
  if (!isModelQuestion(question)) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const model = selectedWordstatAiModel();
  appendWordstatAiMessage('user', question);
  appendWordstatAiMessage('assistant', model, model);
  form.reset();
}, true);
