from __future__ import annotations

from collections.abc import Callable

from scripts.guards import (
    backend_no_print_guard,
    db_artifacts_guard,
    file_line_count_guard,
    no_direct_llm_call_in_api,
    no_secrets_in_repo,
)
from scripts.guards.base import GuardContext, GuardResult

GuardRunner = Callable[[GuardContext], GuardResult]

REGISTRY: dict[str, tuple[str, GuardRunner]] = {
    no_secrets_in_repo.GUARD_ID: (no_secrets_in_repo.DESCRIPTION, no_secrets_in_repo.run),
    db_artifacts_guard.GUARD_ID: (db_artifacts_guard.DESCRIPTION, db_artifacts_guard.run),
    backend_no_print_guard.GUARD_ID: (backend_no_print_guard.DESCRIPTION, backend_no_print_guard.run),
    no_direct_llm_call_in_api.GUARD_ID: (no_direct_llm_call_in_api.DESCRIPTION, no_direct_llm_call_in_api.run),
    file_line_count_guard.GUARD_ID: (file_line_count_guard.DESCRIPTION, file_line_count_guard.run),
}
