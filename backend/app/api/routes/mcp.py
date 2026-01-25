from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from app.api.deps import DbDep, UserIdDep, require_generation_run_viewer
from app.core.errors import AppError, ok_payload
from app.services.mcp.service import list_mcp_tools, replay_mcp_tool_call_and_record

router = APIRouter()


@router.get("/mcp/tools")
def list_tools(request: Request, user_id: UserIdDep) -> dict:
    request_id = request.state.request_id
    _ = user_id
    tools = [{"name": t.name, "description": t.description, "args_schema": t.args_schema} for t in list_mcp_tools()]
    return ok_payload(request_id=request_id, data={"tools": tools})


class McpReplayRequest(BaseModel):
    allowlist: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("allowlist")
    @classmethod
    def _validate_allowlist(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("allowlist items must be strings")
            item = item.strip()
            if not item:
                raise ValueError("allowlist cannot contain empty strings")
            if len(item) > 128:
                raise ValueError("allowlist item too long")
            out.append(item)
        if not out:
            raise ValueError("allowlist is required")
        return out


@router.post("/mcp/runs/{run_id}/replay")
def replay_mcp_run(request: Request, db: DbDep, user_id: UserIdDep, run_id: str, body: McpReplayRequest) -> dict:
    request_id = request.state.request_id
    run = require_generation_run_viewer(db, run_id=run_id, user_id=user_id)
    if run.type != "mcp_tool":
        raise AppError.validation(message="仅支持回放 mcp_tool 类型的 run")

    params_json = (run.params_json or "").strip()
    if not params_json:
        raise AppError.validation(message="缺少原始工具调用参数，无法回放")

    result = replay_mcp_tool_call_and_record(
        request_id=request_id,
        actor_user_id=user_id,
        project_id=str(run.project_id),
        chapter_id=str(run.chapter_id) if run.chapter_id else None,
        original_params_json=params_json,
        allowlist=body.allowlist,
    )
    return ok_payload(
        request_id=request_id,
        data={
            "original_run_id": str(run.id),
            "replay_run_id": result.run_id,
            "tool_name": result.tool_name,
            "ok": result.ok,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "latency_ms": result.latency_ms,
            "truncated": result.truncated,
        },
    )
