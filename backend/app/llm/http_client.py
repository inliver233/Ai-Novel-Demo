from __future__ import annotations

import threading

import httpx

_lock = threading.Lock()
_local = threading.local()
_clients: set[httpx.Client] = set()


def get_llm_http_client() -> httpx.Client:
    client: httpx.Client | None = getattr(_local, "client", None)
    if client is not None and not client.is_closed:
        return client

    client = httpx.Client(trust_env=False)
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
