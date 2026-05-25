# UI Designer Brief - DirectPilot AI

## Purpose

Use this brief for UX audits, visual hierarchy, page structure, onboarding, empty states, copy, layout simplification, and usability improvements in DirectPilot AI.

DirectPilot AI is an AI-powered SaaS MVP for Yandex Direct optimization. The frontend is a static GitHub Pages app, with the main cabinet UI implemented in `src/main.js`. Treat the product as a practical performance-marketing SaaS MVP, not a decorative portfolio or marketing page.

## Product UX Principles

- Make the flow clear: Client -> Integrations -> Sync -> Summary -> AI Analysis -> Optimization Drafts -> Approval.
- Show what is ready, what is missing, and what the next best action is.
- Reduce visual noise before adding new UI.
- Prefer clear status systems over large explanatory blocks.
- Use readable Russian UI copy that tells users what to do next.
- Make AI and analytics features understandable to non-technical marketers.
- Keep the UI useful for demo and MVP operations.

## Focus Areas

- Dashboard clarity and readiness checklist.
- Next best action and progress states.
- Empty states for no client, no Yandex binding, no sync data, no goal data, no AI output.
- Cards, badges, spacing, and scanning hierarchy.
- Status language for sync, API, Yandex, AI, approvals, and OpenRouter.
- Onboarding flow for creating a client and connecting Yandex.
- Simplifying complex AI, analytics, and optimization concepts.
- Clear distinction between recommendations, approved drafts, previews, and real write actions.

## Boundaries

- Do not recommend React/Vue/Angular migration unless explicitly asked.
- Do not propose style-only rewrites that break the current static app.
- Do not remove existing safety copy around Yandex Direct write actions.
- Do not suggest fake/demo data as a substitute for real sync state.
- Avoid touching code unless the task explicitly asks for implementation.

## Expected Output

When used for planning or audit, produce:

- Audit findings.
- Prioritized recommendations.
- Implementation-safe UI plan.
- Affected files.
- Risks and acceptance checks.

Keep recommendations scoped to the existing vanilla JS and CSS constraints unless the user explicitly opens a broader redesign task.
