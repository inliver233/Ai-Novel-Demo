from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.errors import AppError
from app.llm.registry import (
    ContractMode,
    LLMContractLookupError,
    max_context_tokens_limit,
    max_output_tokens_limit,
    pricing_contract,
    recommended_max_tokens,
    resolve_base_url,
    resolve_llm_contract,
)


def current_contract_mode() -> ContractMode:
    raw = str(getattr(settings, "llm_config_mode", "audit") or "audit").strip().lower()
    return "enforce" if raw == "enforce" else "audit"


def _raise_contract_error(exc: LLMContractLookupError) -> None:
    provider = exc.provider
    model = exc.model
    contract_code = exc.code
    details: dict[str, Any] = {"contract_code": contract_code, "contract_mode": current_contract_mode(), **exc.details}
    if provider:
        details.setdefault("provider", provider)
    if model:
        details.setdefault("model", model)

    if contract_code == "provider_required":
        message = "provider 不能为空"
    elif contract_code == "unsupported_provider":
        message = "不支持的 provider"
    elif contract_code == "model_required":
        message = "model 不能为空"
    elif contract_code == "unsupported_model":
        message = "未注册的官方模型，当前模式禁止继续使用"
    elif contract_code == "base_url_required":
        message = f"{provider or '当前 provider'} 必须填写 base_url"
    elif contract_code == "invalid_base_url_scheme":
        message = "base_url 必须以 http:// 或 https:// 开头"
    elif contract_code == "invalid_base_url":
        message = "base_url 不合法"
    else:
        message = "LLM 配置不合法"

    raise AppError(code="LLM_CONFIG_ERROR", message=message, status_code=400, details=details) from exc


def resolve_provider_model(provider: str, model: str, *, mode: ContractMode | None = None):
    active_mode = mode or current_contract_mode()
    try:
        return resolve_llm_contract(provider, model, mode=active_mode)
    except LLMContractLookupError as exc:
        _raise_contract_error(exc)


def normalize_provider_model(provider: str, model: str, *, mode: ContractMode | None = None) -> tuple[str, str]:
    resolution = resolve_provider_model(provider, model, mode=mode)
    return resolution.provider, resolution.model


def normalize_base_url_for_provider(provider: str, base_url: str | None, *, mode: ContractMode | None = None) -> str | None:
    active_mode = mode or current_contract_mode()
    try:
        return resolve_base_url(provider, base_url, mode=active_mode).base_url
    except LLMContractLookupError as exc:
        _raise_contract_error(exc)


def normalize_max_tokens_for_provider(
    provider: str,
    model: str,
    raw_value: int | None,
    *,
    mode: ContractMode | None = None,
) -> int:
    resolution = resolve_provider_model(provider, model, mode=mode)
    if raw_value is None:
        return recommended_max_tokens(resolution.provider, resolution.model, mode=mode or current_contract_mode())
    max_tokens = int(raw_value)
    if max_tokens <= 0:
        raise AppError.validation(message="最大 tokens（max_tokens）必须为正整数")
    limit = max_output_tokens_limit(resolution.provider, resolution.model, mode=mode or current_contract_mode())
    return min(max_tokens, limit) if limit else max_tokens


def contract_metadata(provider: str, model: str, *, mode: ContractMode | None = None) -> dict[str, Any]:
    resolution = resolve_provider_model(provider, model, mode=mode)
    pricing = pricing_contract(resolution.provider, resolution.model, mode=mode or current_contract_mode())
    payload: dict[str, Any] = {
        "provider": resolution.provider,
        "model": resolution.model,
        "provider_key": resolution.provider,
        "model_key": resolution.model_key,
        "known_model": resolution.model_contract is not None,
        "contract_mode": mode or current_contract_mode(),
        "pricing": {},
    }
    if resolution.compatibility_alias:
        payload["compatibility_alias"] = resolution.compatibility_alias
    if resolution.notes:
        payload["contract_notes"] = list(resolution.notes)
    if pricing is not None:
        payload["pricing"] = {
            "input_per_million": pricing.input_per_million,
            "output_per_million": pricing.output_per_million,
            "currency": pricing.currency,
            "source": pricing.source,
        }
    return payload


def capability_contract(provider: str, model: str, *, mode: ContractMode | None = None) -> dict[str, Any]:
    resolution = resolve_provider_model(provider, model, mode=mode)
    active_mode = mode or current_contract_mode()
    metadata = contract_metadata(resolution.provider, resolution.model, mode=active_mode)
    metadata.update(
        {
            "max_tokens_limit": max_output_tokens_limit(resolution.provider, resolution.model, mode=active_mode),
            "max_tokens_recommended": recommended_max_tokens(resolution.provider, resolution.model, mode=active_mode),
            "context_window_limit": max_context_tokens_limit(resolution.provider, resolution.model, mode=active_mode),
        }
    )
    return metadata
