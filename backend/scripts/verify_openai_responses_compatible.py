from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.errors import AppError  # noqa: E402
from app.llm.client import call_llm, call_llm_stream  # noqa: E402


def _mask_secret(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "***"
    return f"{v[:3]}***{v[-4:]}"


def main() -> int:
    provider = (os.getenv("VERIFY_LLM_PROVIDER") or "openai_responses_compatible").strip()
    base_url = (os.getenv("VERIFY_LLM_BASE_URL") or "").strip()
    model = (os.getenv("VERIFY_LLM_MODEL") or "").strip()
    api_key = (os.getenv("VERIFY_LLM_API_KEY") or "").strip()
    if not base_url or not model or not api_key:
        print("Missing env vars: VERIFY_LLM_BASE_URL / VERIFY_LLM_MODEL / VERIFY_LLM_API_KEY", file=sys.stderr)
        return 2

    print(f"provider={provider} base_url={base_url} model={model} api_key={_mask_secret(api_key)}")
    params = {"max_tokens": 64, "temperature": 0}
    system = "You are a connection test."
    user = "Reply with 'pong' only."

    try:
        res = call_llm(
            provider=provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
            system=system,
            user=user,
            params=params,
            timeout_seconds=60,
            extra={},
        )
        print(f"call_llm: ok text={res.text.strip()!r} finish_reason={res.finish_reason!r} dropped={res.dropped_params}")
    except AppError as exc:
        details = getattr(exc, "details", None) or {}
        upstream = details.get("upstream_error")
        if isinstance(upstream, str):
            upstream = upstream.replace("\n", " ")[:300]
        print(f"call_llm: err code={exc.code} status={exc.status_code} upstream={upstream!r}", file=sys.stderr)
        return 1

    try:
        it, st = call_llm_stream(
            provider=provider,
            base_url=base_url,
            model=model,
            api_key=api_key,
            system=system,
            user=user,
            params=params,
            timeout_seconds=60,
            extra={},
        )
        text = "".join(list(it)).strip()
        print(f"call_llm_stream: ok text={text!r} finish_reason={st.finish_reason!r} dropped={st.dropped_params}")
    except AppError as exc:
        details = getattr(exc, "details", None) or {}
        upstream = details.get("upstream_error")
        if isinstance(upstream, str):
            upstream = upstream.replace("\n", " ")[:300]
        print(f"call_llm_stream: err code={exc.code} status={exc.status_code} upstream={upstream!r}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
