# Frontend Developer Brief - DirectPilot AI

## Purpose

Use this brief for implementing frontend changes in `src/main.js` and related static UI files when they are explicitly allowed by the task.

DirectPilot AI currently does not use React, Vue, Angular, Next.js, or Vite. The primary frontend target is vanilla JavaScript in `src/main.js`, hosted as a static GitHub Pages app.

## Responsibilities

- Maintain app state in vanilla JavaScript.
- Preserve input and focus safety.
- Preserve client-scoped state.
- Preserve user/email-scoped localStorage keys.
- Keep AI chat and recommendation state scoped by selected client.
- Maintain navigation through the existing `activeView` model.
- Keep forms stable and editable.
- Improve empty states and status messages without broad redesign.
- Work within existing CSS constraints unless CSS changes are explicitly allowed.
- Keep responsive behavior practical and avoid layout regressions.

## Must Preserve

- GitHub Pages compatibility.
- Backend API base default and `directpilot_api_base` override.
- Login and app authentication flow.
- Existing input click/focus fixes.
- No state leakage between clients or users.
- Authorization headers on protected backend calls.
- Per-client Yandex binding UI behavior.
- AI model settings persistence per email.
- No frontend secrets.

## Implementation Guidance

- Prefer small, targeted changes in `src/main.js`.
- Keep render changes predictable and avoid rerendering on ordinary input clicks.
- Use existing helper functions and state patterns before adding new ones.
- Scope new localStorage keys by email when state can leak across users.
- Scope client-specific UI state by selected client id.
- Add direct, readable Russian copy for user-facing states.
- Keep buttons explicit about whether they navigate, save, preview, or request analysis.

## Checks

Always run:

```bash
npm run build
```

## Avoid

- Introducing React, Vite, framework tooling, or package changes.
- Changing HTML files unless explicitly allowed.
- Broad CSS rewrites without a plan.
- Hiding backend/API errors behind vague copy.
- Showing stale summary, AI, sync, or approval data from another client.
- Adding any Yandex Direct write/apply UI.
