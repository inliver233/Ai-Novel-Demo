from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.llm.registry import (
    ContractMode,
    LLMContractLookupError,
    MODELS_BY_PROVIDER,
    PROVIDER_ALIAS_TO_KEY,
    PROVIDER_CONTRACTS,
    canonical_model_key,
    pricing_contract,
    resolve_base_url,
    resolve_llm_contract,
)
from app.models.llm_preset import LLMPreset
from app.models.llm_profile import LLMProfile
from app.models.llm_task_preset import LLMTaskPreset


@dataclass(frozen=True, slots=True)
class LLMContractFinding:
    severity: str
    source: str
    provider: str | None
    model: str | None
    message: str
    model_key: str | None = None


@dataclass(frozen=True, slots=True)
class LLMContractAuditReport:
    findings: tuple[LLMContractFinding, ...]

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.findings if item.severity == "warning")


def audit_registry() -> list[LLMContractFinding]:
    findings: list[LLMContractFinding] = []
    seen_provider_aliases: set[str] = set()
    for provider in PROVIDER_CONTRACTS:
        for alias in provider.aliases:
            if alias in seen_provider_aliases:
                findings.append(LLMContractFinding("error", "registry", provider.key, None, f"duplicate provider alias: {alias}"))
            seen_provider_aliases.add(alias)
    seen_model_keys: set[str] = set()
    for provider, items in MODELS_BY_PROVIDER.items():
        for item in items:
            if item.key in seen_model_keys:
                findings.append(LLMContractFinding("error", "registry", provider, item.model, f"duplicate model key: {item.key}", model_key=item.key))
            seen_model_keys.add(item.key)
            if pricing_contract(provider, item.model) is None:
                findings.append(LLMContractFinding("warning", "registry", provider, item.model, "pricing contract missing", model_key=item.key))
    for alias, provider in PROVIDER_ALIAS_TO_KEY.items():
        if alias == provider:
            findings.append(LLMContractFinding("error", "registry", provider, None, f"provider alias duplicates canonical key: {alias}"))
    return findings


def audit_rows(rows: Iterable[dict[str, Any]], *, mode: ContractMode = "audit") -> list[LLMContractFinding]:
    findings: list[LLMContractFinding] = []
    for row in rows:
        source = str(row.get("source") or "unknown")
        provider = str(row.get("provider") or "").strip() or None
        model = str(row.get("model") or "").strip() or None
        base_url = row.get("base_url")
        if provider is None or model is None:
            findings.append(LLMContractFinding("warning" if mode == "audit" else "error", source, provider, model, "provider/model missing"))
            continue
        severity = "warning" if mode == "audit" else "error"
        try:
            resolution = resolve_llm_contract(provider, model, mode=mode)
            base_url_resolution = resolve_base_url(provider, base_url if isinstance(base_url, str) else None, mode=mode)
            if resolution.compatibility_alias is not None:
                findings.append(LLMContractFinding("warning", source, resolution.provider, model, f"compatibility alias mapped to {resolution.model}", model_key=resolution.model_key))
            for note in resolution.notes:
                if note in {"unregistered_model", "gateway_passthrough"}:
                    findings.append(LLMContractFinding("warning", source, resolution.provider, resolution.model, note.replace("_", " "), model_key=resolution.model_key))
            if base_url_resolution.note is not None:
                findings.append(LLMContractFinding(severity, source, resolution.provider, resolution.model, base_url_resolution.note, model_key=resolution.model_key))
            if resolution.model_contract is not None and resolution.model_contract.pricing is None:
                findings.append(LLMContractFinding("warning", source, resolution.provider, resolution.model, "pricing contract missing", model_key=resolution.model_key))
            else:
                _ = canonical_model_key(provider, model, mode="audit")
        except LLMContractLookupError as exc:
            findings.append(LLMContractFinding(severity, source, provider, model, exc.code))
    return findings


def audit_database_url(database_url: str, *, mode: ContractMode = "audit") -> LLMContractAuditReport:
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with SessionLocal() as db:
            return audit_session(db, mode=mode)
    finally:
        engine.dispose()


def audit_session(db: Session, *, mode: ContractMode = "audit") -> LLMContractAuditReport:
    rows: list[dict[str, Any]] = []
    for item in db.execute(select(LLMProfile)).scalars():
        rows.append({"source": f"llm_profile:{item.id}", "provider": item.provider, "model": item.model, "base_url": item.base_url})
    for item in db.execute(select(LLMPreset)).scalars():
        rows.append({"source": f"llm_preset:{item.project_id}", "provider": item.provider, "model": item.model, "base_url": item.base_url})
    for item in db.execute(select(LLMTaskPreset)).scalars():
        rows.append({"source": f"llm_task_preset:{item.project_id}:{item.task_key}", "provider": item.provider, "model": item.model, "base_url": item.base_url})
    findings = [*audit_registry(), *audit_rows(rows, mode=mode)]
    return LLMContractAuditReport(findings=tuple(findings))
