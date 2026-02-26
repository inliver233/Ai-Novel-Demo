from __future__ import annotations

import os
import threading

import httpx

_lock = threading.Lock()
_local = threading.local()
_clients: set[httpx.Client] = set()


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def get_llm_http_client() -> httpx.Client:
    client: httpx.Client | None = getattr(_local, "client", None)
    if client is not None and not client.is_closed:
        return client

    trust_env = _env_bool("LLM_HTTP_TRUST_ENV", default=False)
    proxy = str(os.environ.get("LLM_HTTP_PROXY") or "").strip() or None
    if proxy:
        client = httpx.Client(trust_env=trust_env, proxy=proxy)
    else:
        client = httpx.Client(trust_env=trust_env)
    _local.client = client
    with _lock:
        _clients.add(client)
    return client


def close_llm_http_client() -> None:
    with _lock:
        clients = list(_clients)
        _clients.clear()

    for client in clients:
        client.close()
