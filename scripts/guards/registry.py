from __future__ import annotations

from collections.abc import Callable

from scripts.guards import db_artifacts_guard, no_secrets_in_repo
from scripts.guards.base import GuardContext, GuardResult

GuardRunner = Callable[[GuardContext], GuardResult]

REGISTRY: dict[str, tuple[str, GuardRunner]] = {
    no_secrets_in_repo.GUARD_ID: (no_secrets_in_repo.DESCRIPTION, no_secrets_in_repo.run),
    db_artifacts_guard.GUARD_ID: (db_artifacts_guard.DESCRIPTION, db_artifacts_guard.run),
}

