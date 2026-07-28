#!/usr/bin/env node

/**
 * Manual, read-only E2E smoke for a deployed DirectPilot Preview.
 *
 * The script deliberately uses the public audit API exactly as the frontend
 * does. Credentials are supplied only by CI secrets; neither token nor raw
 * Yandex data is printed. Creating an audit stores a job in DirectPilot, but
 * every Yandex Direct operation exercised by it is a read operation.
 */

const required = ['E2E_AUDIT_BASE_URL', 'E2E_AUDIT_SESSION_TOKEN', 'E2E_AUDIT_CLIENT_ID'];
const missing = required.filter((name) => !process.env[name]?.trim());
if (missing.length) {
  throw new Error(`Missing required CI secret(s): ${missing.join(', ')}`);
}

const baseUrl = process.env.E2E_AUDIT_BASE_URL.replace(/\/$/, '');
const maxRuntimeMs = Math.max(60, Number(process.env.E2E_AUDIT_MAX_RUNTIME_SECONDS || 900)) * 1000;
const requiredCapabilities = (process.env.E2E_AUDIT_REQUIRED_CAPABILITIES || '')
  .split(',').map((value) => value.trim()).filter(Boolean);
const bypassSecret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET?.trim();
const startedAt = Date.now();

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function apiUrl(path) {
  return `${baseUrl}/api/v1${path}`;
}

function runtimeOf(job) {
  return job?.context_metadata?.runtime || {};
}

function directCalls(job) {
  return Number(runtimeOf(job).directApiCallsCount || 0);
}

function summarize(job) {
  const runtime = runtimeOf(job);
  const coverage = job?.context_metadata?.canonicalEvidenceCoverage || {};
  const summary = coverage.summary || {};
  return {
    jobId: job?.job_id,
    scope: job?.requested_scope,
    status: job?.status,
    stage: job?.current_stage,
    progress: job?.progress_percent,
    schedulerPhase: runtime.schedulerPhase || null,
    directApiCalls: directCalls(job),
    nextRetryAt: runtime.nextRetryAt || null,
    campaigns: `${summary.coveredCampaigns || 0}/${summary.applicableCampaigns || 0}`,
    rows: {
      received: summary.rowsReceived || 0,
      backend: summary.rowsAnalyzedByBackend || 0,
      ai: summary.rowsSentToAi || 0,
    },
    completionState: job?.context_metadata?.evidenceCoverage?.completionState || null,
  };
}

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      authorization: `Bearer ${process.env.E2E_AUDIT_SESSION_TOKEN}`,
      ...(bypassSecret ? { 'x-vercel-protection-bypass': bypassSecret } : {}),
      ...(options.body ? { 'content-type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail || body || {});
    throw new Error(`${options.method || 'GET'} ${path} failed (${response.status}): ${detail.slice(0, 400)}`);
  }
  return body;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForRetryWindow(job) {
  const retryAt = Date.parse(runtimeOf(job).nextRetryAt || '');
  if (!Number.isFinite(retryAt) || retryAt <= Date.now()) return;

  const before = directCalls(job);
  await sleep(Math.min(5_000, Math.max(1_000, retryAt - Date.now())));
  const waiting = await request(`/ai/audits/${job.job_id}`);
  assert(
    directCalls(waiting) === before,
    `Direct API calls increased before nextRetryAt for ${job.job_id}: ${before} -> ${directCalls(waiting)}`,
  );
}

function validateTerminalAudit(job, scope) {
  assert(job.status === 'completed', `${scope} audit did not complete: ${job.status} (${job.error_code || job.error_message || job.current_stage})`);
  assert(!job.result?.backendFallbackUsed, `${scope} audit completed using backend fallback instead of model analysis`);
  assert(typeof job.answer === 'string' && job.answer.trim().length > 40, `${scope} audit returned no usable final answer`);

  const coverage = job.context_metadata?.canonicalEvidenceCoverage || {};
  const summary = coverage.summary || {};
  const matrix = coverage.campaignMatrix || [];
  assert(matrix.length > 0, `${scope} audit returned no canonical campaign × capability matrix`);
  assert(Number(summary.applicableCampaigns || 0) > 0, `${scope} audit found no applicable campaigns`);
  assert(
    Number(summary.coveredCampaigns || 0) === Number(summary.applicableCampaigns || 0),
    `${scope} breadth coverage incomplete: ${summary.coveredCampaigns || 0}/${summary.applicableCampaigns || 0}`,
  );
  assert(Number(summary.rowsReceived || 0) > 0, `${scope} audit received no Direct rows`);
  assert(Number(summary.rowsAnalyzedByBackend || 0) > 0, `${scope} audit analyzed no rows in backend`);
  assert(Number(summary.rowsSentToAi || 0) > 0, `${scope} audit sent no evidence rows to AI`);
  assert(directCalls(job) > 0, `${scope} audit made no Direct API reads`);

  const capabilityIds = new Set(matrix.map((item) => item.capabilityId));
  if (scope === 'full_account') {
    for (const capability of requiredCapabilities) {
      assert(capabilityIds.has(capability), `${scope} audit did not include required capability: ${capability}`);
    }
    // Search and YAN are intentionally verified by their family-specific
    // baseline capabilities. A short summary has a smaller request budget,
    // so this assertion belongs to the full audit only.
    assert(capabilityIds.has('search_queries'), `${scope} audit has no Search capability (search_queries)`);
    assert(
      capabilityIds.has('placements') || capabilityIds.has('placement_or_network_breakdown'),
      `${scope} audit has no YAN capability (placements or placement_or_network_breakdown)`,
    );
  }
}

async function runScope(scope) {
  const job = await request('/ai/audits', {
    method: 'POST',
    body: JSON.stringify({
      client_id: process.env.E2E_AUDIT_CLIENT_ID,
      scope,
      period: 'last_30_days',
      ai_preset: 'economy',
      max_tokens: 1600,
      cache_policy: 'fresh',
      allow_saved_fallback: false,
      options: {
        include_search_queries: true,
        include_dynamics: true,
        include_tracking: true,
        include_recommendations: true,
      },
    }),
  });
  console.log(JSON.stringify({ event: 'audit_created', ...summarize(job) }));

  const active = await request(`/ai/audits/active?client_id=${encodeURIComponent(process.env.E2E_AUDIT_CLIENT_ID)}`);
  assert(active?.job_id === job.job_id, `Active-audit recovery endpoint did not return the new ${scope} job`);

  let current = job;
  let lastLog = '';
  while (Date.now() - startedAt < maxRuntimeMs) {
    if (['completed', 'failed', 'cancelled'].includes(current.status)) break;
    await waitForRetryWindow(current);

    if (current.status === 'queued' || current.status === 'context_ready') {
      current = await request(`/ai/audits/${current.job_id}/advance`, { method: 'POST', body: '{}' });
    } else {
      const delay = Math.max(1_000, Math.min(15_000, Number(current.poll_after_ms || 1_800)));
      await sleep(delay);
      current = await request(`/ai/audits/${current.job_id}`);
    }
    const logLine = JSON.stringify({ event: 'audit_progress', ...summarize(current) });
    if (logLine !== lastLog) console.log(logLine);
    lastLog = logLine;
  }

  assert(['completed', 'failed', 'cancelled'].includes(current.status), `${scope} audit exceeded ${maxRuntimeMs / 1000}s E2E limit`);
  validateTerminalAudit(current, scope);

  const callsAtFinalization = directCalls(current);
  await sleep(5_000);
  const afterFinalization = await request(`/ai/audits/${current.job_id}`);
  assert(
    directCalls(afterFinalization) === callsAtFinalization,
    `Direct API calls increased after finalization for ${current.job_id}: ${callsAtFinalization} -> ${directCalls(afterFinalization)}`,
  );
  const result = summarize(afterFinalization);
  console.log(JSON.stringify({ event: 'audit_verified', ...result }));
  return result;
}

const scopes = (process.env.E2E_AUDIT_SCOPES || 'full_account,short_summary')
  .split(',').map((value) => value.trim()).filter(Boolean);
assert(scopes.length > 0, 'E2E_AUDIT_SCOPES must contain at least one scope');

const results = [];
for (const scope of scopes) results.push(await runScope(scope));
console.log(JSON.stringify({ event: 'preview_audit_smoke_passed', results }));
