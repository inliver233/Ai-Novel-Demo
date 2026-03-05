---
mode: plan
task: chunk-load-failure resilience and route error UX
created_at: "2026-03-05T19:56:11+08:00"
complexity: medium
---

# Plan: Chunk-load failure resilience and route error UX hardening

## Goal
- Resolve intermittent dynamic import failures across project pages (e.g., prompts page) with self-healing behavior.
- Replace default React Router crash UX with project-specific route error page.

## Scope
- In:
  - Add dynamic import retry/recover utility for lazy-loaded route pages.
  - Add global route error element for actionable UX when route rendering fails.
  - Update frontend nginx cache policy to reduce stale index/chunk mismatch probability.
  - Run targeted regression for multi-page navigation and auth form submit.
- Out:
  - No backend API/data model changes.

## Assumptions / Dependencies
- Branch is `test`.
- Issue focuses on frontend runtime resilience + deploy cache behavior.

## Phases
1. Implement lazy-import recovery utility and wire into route lazy definitions.
2. Add route error page and attach `errorElement` to major route roots.
3. Update nginx static cache headers for `index.html` and `/assets/`.
4. Run frontend and UI smoke tests for pages including prompts.

## Tests & Verification
- `cd frontend && npm run lint && npm test && npm run build`
- `cd test && npx playwright test specs/ui/auth-form-submit.spec.ts specs/ui/navigation.spec.ts`

## Issue CSV
- Path: issues/2026-03-05_19-56-11-chunk-load-resilience-and-error-ux.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Dynamic import chunk-load failures auto-recover once via controlled reload.
- [ ] Route crash page uses custom UX instead of default React Router message.
- [ ] Index/assets cache policy is explicit and deployment-friendly.
- [ ] Navigation smoke including prompts page passes.

## Risks / Blockers
- Multi-instance rollout without shared static assets can still cause transient mismatch; auto-recover + better cache policy mitigates but does not replace proper rollout strategy.

## Rollback / Recovery
- Revert by commit: `git revert <commit>`.

## Checkpoints
- Commit after: MVP-619

## References
- frontend/src/App.tsx
- frontend/nginx.conf
- test/specs/ui/navigation.spec.ts
