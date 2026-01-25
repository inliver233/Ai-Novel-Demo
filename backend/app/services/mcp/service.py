from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Callable

from app.llm.redaction import redact_text
from app.services.run_store import write_generation_run

_DEFAULT_TIMEOUT_SECONDS = 6.0
_DEFAULT_MAX_OUTPUT_CHARS = 6000
_MAX_TOOL_CALLS = 6


@dataclass(frozen=True, slots=True)
class McpToolSpec:
    name: str
    description: str
    args_schema: dict[str, object]


@dataclass(frozen=True, slots=True)
class McpToolCall:
    tool_name: str
    args: dict[str, object]


@dataclass(frozen=True, slots=True)
class McpToolCallResult:
    run_id: str
    tool_name: str
    ok: bool
    output_text: str
    error_code: str | None
    error_message: str | None
    latency_ms: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class McpResearchConfig:
    enabled: bool
    allowlist: list[str]
    calls: list[McpToolCall]
    timeout_seconds: float | None = None
    max_output_chars: int | None = None


_ToolRunner = Callable[[dict[str, object]], str]


@dataclass(frozen=True, slots=True)
class _Tool:
    spec: McpToolSpec
    run: _ToolRunner


def _json_safe(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(item) for item in value[:200]]
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in list(value.items())[:200]:
            out[str(k)] = _json_safe(v)
        return out
    return str(value)


def _redact_obj(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_obj(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _redact_obj(v) for k, v in value.items()}
    return value


def _tool_mock_echo(args: dict[str, object]) -> str:
    return str(args.get("text") or "")


def _tool_mock_sleep(args: dict[str, object]) -> str:
    seconds = args.get("seconds")
    try:
        sec = float(seconds) if seconds is not None else 0.0
    except Exception:
        sec = 0.0
    if sec < 0:
        sec = 0.0
    time.sleep(sec)
    return f"slept:{sec}"


def _tool_mock_fail(_args: dict[str, object]) -> str:
    raise RuntimeError("mock_fail")


_TOOLS: dict[str, _Tool] = {
    "mock.echo": _Tool(
        spec=McpToolSpec(
            name="mock.echo",
            description="Mock tool: returns args.text (for tests/demos).",
            args_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        ),
        run=_tool_mock_echo,
    ),
    "mock.sleep": _Tool(
        spec=McpToolSpec(
            name="mock.sleep",
            description="Mock tool: sleeps for args.seconds (for timeout tests).",
            args_schema={"type": "object", "properties": {"seconds": {"type": "number"}}, "required": ["seconds"]},
        ),
        run=_tool_mock_sleep,
    ),
    "mock.fail": _Tool(
        spec=McpToolSpec(
            name="mock.fail",
            description="Mock tool: raises an exception (for fail-soft tests).",
            args_schema={"type": "object", "properties": {}},
        ),
        run=_tool_mock_fail,
    ),
}


def list_mcp_tools() -> list[McpToolSpec]:
    return [t.spec for t in _TOOLS.values()]


def _resolve_tool(tool_name: str) -> _Tool | None:
    return _TOOLS.get(tool_name)


def _run_with_timeout(*, fn: Callable[[], str], timeout_seconds: float) -> str:
    if timeout_seconds <= 0:
        timeout_seconds = _DEFAULT_TIMEOUT_SECONDS
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn)
        return fut.result(timeout=timeout_seconds)


def run_mcp_tool_call_and_record(
    *,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    chapter_id: str | None,
    tool_name: str,
    args: dict[str, object] | None,
    allowlist: list[str] | None,
    timeout_seconds: float | None = None,
    max_output_chars: int | None = None,
    purpose: str | None = None,
) -> McpToolCallResult:
    tool_name = str(tool_name or "").strip()
    safe_allowlist = [str(x).strip() for x in (allowlist or []) if isinstance(x, str) and x.strip()]
    args_dict = args or {}
    safe_args = _json_safe(args_dict)

    err_code: str | None = None
    err_msg: str | None = None
    ok = False
    truncated = False
    output_text = ""
    latency_ms = 0

    timeout = float(timeout_seconds) if timeout_seconds is not None else _DEFAULT_TIMEOUT_SECONDS
    out_limit = int(max_output_chars) if max_output_chars is not None else _DEFAULT_MAX_OUTPUT_CHARS
    if out_limit < 0:
        out_limit = 0

    tool = _resolve_tool(tool_name)
    if not safe_allowlist:
        err_code, err_msg = "ALLOWLIST_REQUIRED", "allowlist is required"
    elif tool is None:
        err_code, err_msg = "TOOL_NOT_FOUND", "tool not found"
    elif tool_name not in safe_allowlist:
        err_code, err_msg = "TOOL_NOT_ALLOWED", "tool not in allowlist"
    else:
        start = time.monotonic()
        try:
            raw = _run_with_timeout(fn=lambda: tool.run(args_dict), timeout_seconds=timeout)
            output_text = str(raw or "")
            ok = True
        except FuturesTimeoutError:
            err_code, err_msg = "TOOL_TIMEOUT", f"timeout after {timeout}s"
        except Exception as exc:
            err_code, err_msg = "TOOL_ERROR", str(exc)[:200]
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)

    output_text = redact_text(output_text or "")
    if out_limit == 0:
        truncated = bool(output_text.strip())
        output_text = ""
    elif len(output_text) > out_limit:
        output_text = output_text[:out_limit].rstrip() + "\n...[truncated]"
        truncated = True

    params_obj: dict[str, Any] = {
        "tool_name": tool_name,
        "args": _redact_obj(safe_args),
        "timeout_seconds": timeout,
        "max_output_chars": out_limit,
    }
    if purpose:
        params_obj["purpose"] = str(purpose)[:200]
    params_json = json.dumps(params_obj, ensure_ascii=False)

    error_json = None
    if not ok:
        error_json = json.dumps({"code": err_code or "TOOL_ERROR", "message": err_msg or "tool failed"}, ensure_ascii=False)

    run_id = write_generation_run(
        request_id=request_id,
        actor_user_id=actor_user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        run_type="mcp_tool",
        provider=None,
        model=None,
        prompt_system="",
        prompt_user="",
        prompt_render_log_json=None,
        params_json=params_json,
        output_text=output_text if ok else None,
        error_json=error_json,
    )
    return McpToolCallResult(
        run_id=run_id,
        tool_name=tool_name,
        ok=ok,
        output_text=output_text,
        error_code=err_code,
        error_message=err_msg,
        latency_ms=latency_ms,
        truncated=truncated,
    )


def replay_mcp_tool_call_and_record(
    *,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    chapter_id: str | None,
    original_params_json: str,
    allowlist: list[str] | None,
) -> McpToolCallResult:
    try:
        params = json.loads(original_params_json or "{}")
    except Exception:
        params = {}
    tool_name = str((params or {}).get("tool_name") or "").strip()
    args = (params or {}).get("args")
    if not isinstance(args, dict):
        args = {}
    timeout = (params or {}).get("timeout_seconds")
    max_chars = (params or {}).get("max_output_chars")
    return run_mcp_tool_call_and_record(
        request_id=request_id,
        actor_user_id=actor_user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        tool_name=tool_name,
        args=args,  # type: ignore[arg-type]
        allowlist=allowlist,
        timeout_seconds=float(timeout) if timeout is not None else None,
        max_output_chars=int(max_chars) if max_chars is not None else None,
        purpose="replay",
    )


def run_mcp_research_and_record(
    *,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    chapter_id: str | None,
    config: McpResearchConfig,
) -> tuple[str, list[McpToolCallResult], list[str]]:
    if not config.enabled:
        return "", [], []

    allowlist = [str(x).strip() for x in (config.allowlist or []) if isinstance(x, str) and x.strip()]
    if not allowlist:
        return "", [], ["mcp_allowlist_required"]
    calls = list(config.calls or [])[:_MAX_TOOL_CALLS]
    warnings: list[str] = []
    if (config.calls or []) and len(config.calls) > _MAX_TOOL_CALLS:
        warnings.append("mcp_call_limit_truncated")

    results: list[McpToolCallResult] = []
    parts: list[str] = []
    for call in calls:
        name = str(call.tool_name or "").strip()
        if not name:
            warnings.append("mcp_call_invalid_tool_name")
            continue
        res = run_mcp_tool_call_and_record(
            request_id=request_id,
            actor_user_id=actor_user_id,
            project_id=project_id,
            chapter_id=chapter_id,
            tool_name=name,
            args=call.args,
            allowlist=allowlist,
            timeout_seconds=config.timeout_seconds,
            max_output_chars=config.max_output_chars,
            purpose="research",
        )
        results.append(res)
        if res.ok and res.output_text.strip():
            parts.append(f"【{res.tool_name}】\n{res.output_text.strip()}")
        if not res.ok:
            warnings.append(f"mcp_tool_failed:{res.tool_name}:{res.error_code or 'TOOL_ERROR'}")

    context = "\n\n".join(parts).strip()
    return context, results, warnings
