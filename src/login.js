const app = document.querySelector('#app');
const DEFAULT_PRODUCTION_API_BASE = 'https://directpilot-ai.vercel.app/api/v1';
const API_BASE = resolveApiBase();

let authStep = 'email';
let authLoading = false;
let devCode = null;

function resolveApiBase() {
  const custom = window.localStorage.getItem('directpilot_api_base')?.trim();
  if (custom) return custom.replace(/\/$/, '');

  const { hostname, origin } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8000/api/v1';
  }
  if (hostname === 'maximusb93.github.io') {
    return DEFAULT_PRODUCTION_API_BASE;
  }

  return `${origin}/api/v1`;
}

function hasCustomApiBase() {
  return Boolean(window.localStorage.getItem('directpilot_api_base')?.trim());
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function backendConnectionError() {
  return `Не удалось подключиться к backend. Проверьте Vercel URL или directpilot_api_base. Текущий API_BASE: ${API_BASE}`;
}

function render() {
  const githubPagesWarning = window.location.hostname === 'maximusb93.github.io' && API_BASE.includes('github.io/api/v1')
    ? '<div class="authStatus aiError">GitHub Pages не содержит backend. Укажите Vercel backend URL.</div>'
    : '';

  app.innerHTML = `
    <section class="authPage">
      <a class="brand authBrand" href="index.html">
        <span class="brandIcon">✦</span>
        DirectPilot AI
      </a>
      <div class="authCard">
        <span class="eyebrow">🔐 Вход по email-коду</span>
        <h1>Войдите в личный кабинет</h1>
        <p>Мы отправим одноразовый код на почту. После подтверждения откроется отдельная страница кабинета.</p>

        <form class="authForm" data-auth-form>
          <div class="authField">
            <label for="login-email">Email</label>
            <input id="login-email" type="email" name="email" placeholder="you@agency.ru" autocomplete="email" inputmode="email" autofocus required />
          </div>
          <div class="authField" data-code-field hidden>
            <label for="login-code">Код из письма</label>
            <input id="login-code" type="text" name="code" inputmode="numeric" maxlength="6" placeholder="000000" autocomplete="one-time-code" />
          </div>
          <button class="primaryButton" type="submit" data-auth-submit>Получить код</button>
        </form>

        <div class="authStatus" data-auth-status hidden></div>
        <div class="authStatus dev" data-dev-code hidden></div>

        <section class="panel backendApiConfig">
          <div class="panelHeader">
            <div>
              <h3>Backend API URL</h3>
              <p>Текущий Backend API URL: <code>${escapeHtml(API_BASE)}</code></p>
            </div>
          </div>
          ${githubPagesWarning}
          <div class="authForm" data-api-base-config>
            <div class="authField">
              <label for="backend-api-base">Backend API URL</label>
              <input id="backend-api-base" type="text" data-api-base-input data-debug-name="backend-api-base" value="${escapeHtml(API_BASE)}" placeholder="https://your-backend.vercel.app/api/v1" autocomplete="url" />
            </div>
            <button class="secondaryButton" type="button" data-save-api-base>Сохранить backend URL</button>
          </div>
        </section>

        <a class="secondaryButton" href="index.html">← На главную</a>
      </div>
    </section>
  `;
}

function setStatus(message, isError = false) {
  const status = app.querySelector('[data-auth-status]');
  status.hidden = !message;
  status.textContent = message || '';
  status.classList.toggle('aiError', Boolean(isError));
}

function setDevCode(code) {
  const devCodeElement = app.querySelector('[data-dev-code]');
  devCode = code || null;
  devCodeElement.hidden = !devCode;
  devCodeElement.textContent = devCode ? `Код для MVP/dev режима: ${devCode}` : '';
}

function setLoading(isLoading) {
  authLoading = isLoading;
  const submitButton = app.querySelector('[data-auth-submit]');
  submitButton.disabled = authLoading;
  submitButton.textContent = authLoading
    ? 'Отправляем...'
    : authStep === 'code'
      ? 'Подтвердить код'
      : 'Получить код';
}

function showCodeStep() {
  authStep = 'code';
  const codeField = app.querySelector('[data-code-field]');
  const codeInput = app.querySelector('input[name="code"]');
  codeField.hidden = false;
  codeInput.required = true;
  setLoading(false);
  codeInput.focus({ preventScroll: true });
}

async function requestEmailCode(email) {
  try {
    const response = await fetch(`${API_BASE}/auth/email/request-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось отправить код');
    return payload;
  } catch (error) {
    throw new Error(backendConnectionError());
  }
}

async function verifyEmailCode(email, code) {
  try {
    const response = await fetch(`${API_BASE}/auth/email/verify-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, code }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || 'Не удалось подтвердить код');
    return payload;
  } catch (error) {
    throw new Error(`${error.message}. Текущий API_BASE: ${API_BASE}`);
  }
}

render();

app.querySelector('[data-save-api-base]').addEventListener('click', () => {
  const apiBaseConfig = app.querySelector('[data-api-base-config]');
  const apiBaseInput = apiBaseConfig.querySelector('[data-api-base-input]');
  const apiBase = String(apiBaseInput.value || '').trim().replace(/\/$/, '');
  if (apiBase) {
    localStorage.setItem('directpilot_api_base', apiBase);
  } else {
    localStorage.removeItem('directpilot_api_base');
  }
  window.location.reload();
});

app.querySelector('[data-auth-form]').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (authLoading) return;

  const emailInput = app.querySelector('input[name="email"]');
  const codeInput = app.querySelector('input[name="code"]');
  const email = emailInput.value.trim();
  const code = codeInput.value.trim();

  setLoading(true);
  setStatus('Отправляем запрос...');

  try {
    if (authStep === 'email') {
      const result = await requestEmailCode(email);
      setDevCode(result.dev_code);
      setStatus('Код отправлен на почту. Проверьте входящие и спам.');
      showCodeStep();
      return;
    }

    const result = await verifyEmailCode(email, code);
    localStorage.setItem('directpilot_session', result.session_token);
    localStorage.setItem('directpilot_email', result.email);
    window.location.href = 'app.html';
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setLoading(false);
  }
});
