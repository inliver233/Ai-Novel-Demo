from __future__ import annotations

from collections.abc import Callable

from scripts.guards import (
    backend_no_print_guard,
    db_artifacts_guard,
    deployment_security_guard,
    file_line_count_guard,
    no_direct_llm_call_in_api,
    no_secrets_in_repo,
    prompt_preset_integrity_guard,
)
from scripts.guards.base import GuardContext, GuardResult

GuardRunner = Callable[[GuardContext], GuardResult]

REGISTRY: dict[str, tuple[str, GuardRunner]] = {
    no_secrets_in_repo.GUARD_ID: (no_secrets_in_repo.DESCRIPTION, no_secrets_in_repo.run),
    db_artifacts_guard.GUARD_ID: (db_artifacts_guard.DESCRIPTION, db_artifacts_guard.run),
    deployment_security_guard.GUARD_ID: (
        deployment_security_guard.DESCRIPTION,
        deployment_security_guard.run,
    ),
    backend_no_print_guard.GUARD_ID: (backend_no_print_guard.DESCRIPTION, backend_no_print_guard.run),
    no_direct_llm_call_in_api.GUARD_ID: (no_direct_llm_call_in_api.DESCRIPTION, no_direct_llm_call_in_api.run),
    file_line_count_guard.GUARD_ID: (file_line_count_guard.DESCRIPTION, file_line_count_guard.run),
    prompt_preset_integrity_guard.GUARD_ID: (
        prompt_preset_integrity_guard.DESCRIPTION,
        prompt_preset_integrity_guard.run,
    ),
}
