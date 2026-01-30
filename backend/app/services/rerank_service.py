from __future__ import annotations

import time
from typing import Any, Callable

from app.core.config import settings
from app.llm.http_client import get_llm_http_client
from app.llm.utils import normalize_base_url


def _external_rerank_candidates(
    *,
    query_text: str,
    candidates: list[dict[str, Any]],
    external: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base_url_raw = str((external or {}).get("base_url") or "").strip() if isinstance(external, dict) else ""
    if not base_url_raw:
        base_url_raw = str(getattr(settings, "vector_rerank_external_base_url", "") or "").strip()
    if not base_url_raw:
        raise RuntimeError("external_rerank_api base_url not configured")

    base_url = normalize_base_url(base_url_raw)
    url = base_url if base_url.endswith("/rerank") else base_url + "/rerank"

    model = str((external or {}).get("model") or "").strip() if isinstance(external, dict) else ""
    if not model:
        model = str(getattr(settings, "vector_rerank_external_model", "") or "").strip()
    model = model or None

    api_key = str((external or {}).get("api_key") or "").strip() if isinstance(external, dict) else ""
    if not api_key:
        api_key = str(getattr(settings, "vector_rerank_external_api_key", "") or "").strip()
    api_key = api_key or None

    timeout_raw = (external or {}).get("timeout_seconds") if isinstance(external, dict) else None
    try:
        timeout_s = float(timeout_raw) if timeout_raw is not None else float(getattr(settings, "vector_rerank_external_timeout_seconds", 15.0) or 15.0)
    except Exception:
        timeout_s = float(getattr(settings, "vector_rerank_external_timeout_seconds", 15.0) or 15.0)
    timeout_s = max(1.0, min(timeout_s, 120.0))

    docs = [str(c.get("text") or "") for c in candidates if isinstance(c, dict)]
    payload = {"model": model, "query": query_text, "documents": docs}
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    client = get_llm_http_client()
    resp = client.post(url, headers=headers, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()

    items: list[object] | None = None
    if isinstance(data, dict):
        if isinstance(data.get("results"), list):
            items = data["results"]
        elif isinstance(data.get("data"), list):
            items = data["data"]
    elif isinstance(data, list):
        items = data

    if not isinstance(items, list):
        raise RuntimeError("bad external rerank response: missing results")

    scores: dict[int, float] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_idx = item.get("index")
        if raw_idx is None:
            raw_idx = item.get("idx")
        if raw_idx is None:
            raw_idx = item.get("document_index")
        raw_score = item.get("score")
        if raw_score is None:
            raw_score = item.get("relevance_score")
        if raw_score is None:
            raw_score = item.get("similarity")

        if isinstance(raw_idx, bool) or raw_idx is None:
            continue
        if isinstance(raw_score, bool) or raw_score is None:
            continue
        try:
            idx = int(raw_idx)
            score = float(raw_score)
        except Exception:
            continue
        if idx < 0 or idx >= len(candidates):
            continue
        prev = scores.get(idx)
        if prev is None or score > prev:
            scores[idx] = score

    if not scores:
        raise RuntimeError("bad external rerank response: empty scores")

    order = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    seen: set[int] = set()
    reranked: list[dict[str, Any]] = []
    for idx, _score in order:
        seen.add(idx)
        reranked.append(candidates[idx])
    for idx, c in enumerate(candidates):
        if idx not in seen:
            reranked.append(c)

    return reranked, {"provider": "external_rerank_api", "model": model}


def rerank_candidates(
    *,
    query_text: str,
    candidates: list[dict[str, Any]],
    method: str,
    top_k: int,
    score_fn: Callable[..., float],
    hybrid_alpha: float | None = None,
    external: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before = [str(c.get("id") or "") for c in candidates if isinstance(c, dict)]
    start = time.perf_counter()

    qtext = (query_text or "").strip()
    requested_method = str(method or "").strip() or "auto"
    alpha: float | None
    if hybrid_alpha is None:
        alpha = None
    else:
        try:
            alpha = float(hybrid_alpha)
        except Exception:
            alpha = None
    if alpha is not None:
        alpha = max(0.0, min(float(alpha), 1.0))
    try:
        limit = int(top_k)
    except Exception:
        limit = 0
    if limit <= 0:
        limit = len(candidates)
    limit = max(0, min(int(limit), int(len(candidates))))

    base_obs: dict[str, Any] = {
        "enabled": True,
        "applied": False,
        "requested_method": requested_method,
        "method": None,
        "provider": None,
        "model": None,
        "top_k": int(limit),
        "hybrid_alpha": alpha,
        "hybrid_applied": False,
        "after_rerank": list(before),
        "reason": None,
        "error_type": None,
        "before": before,
        "after": list(before),
        "timing_ms": 0,
        "errors": [],
    }

    if not qtext or not candidates:
        obs = dict(base_obs)
        obs["reason"] = "empty_query_or_candidates"
        obs["timing_ms"] = int((time.perf_counter() - start) * 1000)
        return list(candidates), obs

    errors: list[dict[str, str]] = []

    plan: list[str]
    if requested_method == "auto":
        plan = ["rapidfuzz_token_set_ratio", "token_overlap"]
    elif requested_method == "rapidfuzz_token_set_ratio":
        plan = ["rapidfuzz_token_set_ratio", "token_overlap"]
    elif requested_method == "token_overlap":
        plan = ["token_overlap"]
    elif requested_method == "external_rerank_api":
        plan = ["external_rerank_api", "rapidfuzz_token_set_ratio", "token_overlap"]
    else:
        errors.append({"method": requested_method, "reason": "unknown_method", "error": "ValueError"})
        plan = ["rapidfuzz_token_set_ratio", "token_overlap"]

    head = candidates[:limit]
    tail = candidates[limit:]

    for try_method in plan:
        if try_method == "external_rerank_api":
            try:
                reranked_head, ext = _external_rerank_candidates(query_text=qtext, candidates=head, external=external)
                reranked = list(reranked_head) + list(tail)
                after_rerank = [str(c.get("id") or "") for c in reranked if isinstance(c, dict)]
                final = list(reranked)
                after = list(after_rerank)
                hybrid_applied = False
                if alpha is not None and alpha > 0.0:
                    base_rank = {cid: idx for idx, cid in enumerate(before, start=1) if cid}
                    rerank_rank = {cid: idx for idx, cid in enumerate(after_rerank, start=1) if cid}

                    def _key(c: dict[str, Any]) -> tuple[float, int, int, str]:
                        cid = str(c.get("id") or "")
                        br = int(base_rank.get(cid, 10**9))
                        rr = int(rerank_rank.get(cid, 10**9))
                        score = float(alpha) * float(br) + (1.0 - float(alpha)) * float(rr)
                        return (score, rr, br, cid)

                    final = sorted(final, key=_key)
                    after = [str(c.get("id") or "") for c in final if isinstance(c, dict)]
                    hybrid_applied = after != after_rerank
                obs = dict(base_obs)
                obs.update(
                    {
                        "applied": after != before,
                        "method": "external_rerank_api",
                        "provider": ext.get("provider"),
                        "model": ext.get("model"),
                        "reason": "ok",
                        "after": after,
                        "after_rerank": after_rerank,
                        "hybrid_applied": bool(hybrid_applied),
                        "timing_ms": int((time.perf_counter() - start) * 1000),
                        "errors": errors,
                    }
                )
                return final, obs
            except Exception as exc:
                errors.append({"method": "external_rerank_api", "reason": "error", "error": type(exc).__name__})
                continue

        if try_method not in {"rapidfuzz_token_set_ratio", "token_overlap"}:
            errors.append({"method": try_method, "reason": "unknown_method", "error": "ValueError"})
            continue

        try:
            scored: list[tuple[float, int, dict[str, Any]]] = []
            for idx, c in enumerate(head):
                if not isinstance(c, dict):
                    continue
                score = float(score_fn(method=try_method, query_text=qtext, candidate_text=str(c.get("text") or "")))
                scored.append((score, idx, c))

            scored.sort(key=lambda x: (-x[0], x[1]))
            reranked_head = [c for _score, _idx, c in scored]
            reranked = list(reranked_head) + list(tail)
            after_rerank = [str(c.get("id") or "") for c in reranked if isinstance(c, dict)]
            final = list(reranked)
            after = list(after_rerank)
            hybrid_applied = False
            if alpha is not None and alpha > 0.0:
                base_rank = {cid: idx for idx, cid in enumerate(before, start=1) if cid}
                rerank_rank = {cid: idx for idx, cid in enumerate(after_rerank, start=1) if cid}

                def _key(c: dict[str, Any]) -> tuple[float, int, int, str]:
                    cid = str(c.get("id") or "")
                    br = int(base_rank.get(cid, 10**9))
                    rr = int(rerank_rank.get(cid, 10**9))
                    score = float(alpha) * float(br) + (1.0 - float(alpha)) * float(rr)
                    return (score, rr, br, cid)

                final = sorted(final, key=_key)
                after = [str(c.get("id") or "") for c in final if isinstance(c, dict)]
                hybrid_applied = after != after_rerank
            obs = dict(base_obs)
            obs.update(
                {
                    "applied": after != before,
                    "method": try_method,
                    "provider": "local",
                    "model": None,
                    "reason": "ok",
                    "after": after,
                    "after_rerank": after_rerank,
                    "hybrid_applied": bool(hybrid_applied),
                    "timing_ms": int((time.perf_counter() - start) * 1000),
                    "errors": errors,
                }
            )
            return final, obs
        except ImportError as exc:
            errors.append({"method": try_method, "reason": "dependency_missing", "error": type(exc).__name__})
        except Exception as exc:
            errors.append({"method": try_method, "reason": "error", "error": type(exc).__name__})

    obs = dict(base_obs)
    obs["reason"] = "failed"
    obs["timing_ms"] = int((time.perf_counter() - start) * 1000)
    obs["errors"] = errors
    if errors:
        obs["error_type"] = str(errors[0].get("error") or "") or None
    return list(candidates), obs
