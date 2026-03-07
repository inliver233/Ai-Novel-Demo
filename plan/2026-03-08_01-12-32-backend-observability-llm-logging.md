---
mode: plan
task: "Backend observability: timezone bug audit + llm logging"
created_at: "2026-03-08T01:12:32.4707436+08:00"
complexity: medium
---

# Goal
- Verify the reported `last_generation_at` naive/aware datetime crash in the current `test` branch, preserve the existing fix with executable evidence, and make LLM/provider failure paths observable enough for local debugging without leaking secrets.
- Establish a backend logging foundation based on `loguru` while keeping existing structured JSON event logging and request correlation behavior intact.

## Scope
- In:
  - Audit `backend/app/services/user_usage_service.py` and its callers to confirm the cited aware-vs-naive comparison root cause, current fix state, and regression evidence.
  - Improve backend observability for `/api/llm/test` and shared LLM call failures so provider/model/base-url host/attempt summaries/upstream status become visible in terminal logs.
  - Introduce `loguru` as the backend logging sink/interceptor and keep secret redaction + request ID propagation.
  - Add or update the minimum backend tests needed to lock the behavior.
- Out:
  - Frontend UI changes or new product features unrelated to observability/debugging.
  - Broad refactors of all service modules or changing API response contracts beyond safe diagnostic fields.
  - Full repo-wide logging migration of every callsite to a new API.

## Assumptions / Dependencies
- Work stays on branch `test`.
- The current branch may already contain a fix for the cited timezone comparison; if so, preserve it with validation instead of rewriting it.
- Local backend virtualenv exists at `backend/.venv` and is the source of truth for verification.
- Logging must not expose raw API keys/tokens; only masked/safe fields are allowed.

## Phases
1. Audit the timezone bug, call chain, and current regression coverage.
2. Improve LLM failure detail propagation and terminal-visible structured logs.
3. Introduce `loguru` logging bootstrap/interception while preserving current structured log helpers.
4. Run targeted backend verification, update Issue CSV statuses, and summarize risk.

## Tests & Verification
- Timezone regression + LLM route logging -> `cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_user_usage_stats tests.test_llm_test_endpoint_retry_details tests.test_llm_client_logging -v`
- Logging bootstrap/redaction -> `cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_logging_redaction tests.test_logging_setup -v`
- Compile safety -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic`

## Issue CSV
- Path: issues/2026-03-08_01-12-32-backend-observability-llm-logging.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- `none` for implementation rows; use repo-local shell/tests only.

## Acceptance Checklist
- [ ] The reported aware-vs-naive `last_generation_at` failure is investigated with concrete code/test evidence and does not regress on the current branch.
- [ ] `/api/llm/test` and shared LLM failures emit terminal-visible structured logs with safe provider/model/base-url host/retry context.
- [ ] Backend logging is bootstrapped through `loguru` and standard library loggers flow through the same sink.
- [ ] Secret redaction and request ID correlation remain intact.
- [ ] Targeted backend tests and compile checks pass.

## Risks / Blockers
- Over-logging upstream payloads could leak secrets; safe-field allowlisting and redaction must stay strict.
- Logging interception can duplicate logs if existing handlers are not normalized correctly.
- Adding `loguru` changes runtime bootstrap and may require dependency lock updates.

## Rollback / Recovery
- Revert the observability-specific backend files and dependency entries if logging interception causes duplicate or missing logs.
- Keep the timezone bug audit isolated so existing production-safe logic is not rewritten without evidence.

## Checkpoints
- Commit after: `MVP-650` and `MVP-651` separately once code + Issue CSV updates are ready (not executed in this session unless explicitly requested).

## References
- `AGENTS.md:1`
- `issues/README.md:1`
- `docs/testing-policy.md:1`
- `backend/app/services/user_usage_service.py:1`
- `backend/tests/test_user_usage_stats.py:1`
- `backend/app/api/routes/llm.py:1`
- `backend/app/llm/client.py:1`
- `backend/app/core/logging.py:1`
- `backend/app/main.py:1`
