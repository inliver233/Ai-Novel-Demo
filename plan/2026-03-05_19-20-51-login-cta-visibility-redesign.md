---
mode: plan
task: login register cta visibility redesign
created_at: "2026-03-05T19:20:51+08:00"
complexity: low
---

# Plan: Login page register CTA visibility redesign

## Goal
- Improve visual prominence of register entry on login page.
- Make register action and LinuxDo login/register action same hierarchy.

## Scope
- In:
  - Redesign CTA area on login page to present two peer actions: local register and LinuxDo one-click login/register.
  - Add clear color differentiation and interaction states while keeping existing theme system.
- Out:
  - No backend/auth flow change.
  - No register page business logic change.

## Assumptions / Dependencies
- Existing route `/register` remains unchanged.
- Existing LinuxDo provider check flow remains unchanged.

## Phases
1. Refactor login CTA section into two equal-level buttons.
2. Keep existing submit and LinuxDo behavior; adjust only presentation/layout.
3. Run frontend validation and targeted UI regression.

## Tests & Verification
- `cd frontend && npm run lint && npm test && npm run build`
- `cd test && npx playwright test specs/ui/auth-form-submit.spec.ts`

## Issue CSV
- Path: issues/2026-03-05_19-20-51-login-cta-visibility-redesign.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Login page shows register and LinuxDo actions as same-level CTAs.
- [ ] Register CTA is visually prominent and readable on light theme.
- [ ] Existing login submit behavior still works.
- [ ] Frontend checks and targeted UI spec pass.

## Risks / Blockers
- Minor style conflicts on very small screens; mitigated by responsive one-column fallback.

## Rollback / Recovery
- Revert by commit: `git revert <commit>`.

## Checkpoints
- Commit after: MVP-618

## References
- frontend/src/pages/LoginPage.tsx
- test/specs/ui/auth-form-submit.spec.ts
