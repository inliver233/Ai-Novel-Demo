from __future__ import annotations

import re
from datetime import datetime, timezone
from random import Random
from typing import Any

from jinja2 import Environment, meta

_MACRO_TOKEN_RE = re.compile(r"{{\s*(//[^\n]*|[a-zA-Z0-9_]+)(?:::(.*?))?\s*}}", flags=re.DOTALL)

_ESCAPE_MACRO_RE = re.compile(
    r"{{\s*(//[^\n]*|random::.*?|pick::.*?|date|time|isodate)\s*}}",
    flags=re.DOTALL,
)

_JINJA = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)


def _escape_macros(template: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal counter
        token = match.group(0)
        key = f"__AINOVEL_MACRO_{counter}__"
        counter += 1
        mapping[key] = token
        return key

    escaped = _ESCAPE_MACRO_RE.sub(_replace, template)
    return escaped, mapping


def _restore_macros(text: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return text
    out = text
    for key, token in mapping.items():
        out = out.replace(key, token)
    return out


def _evaluate_macros(text: str, *, seed: str | None = None) -> str:
    """
    Macro layer (after template render).

    Supported (v1):
    - {{date}} / {{time}} / {{isodate}}
    - {{random::A::B}} (non-deterministic)
    - {{pick::A::B}}   (deterministic within one render if seed provided)
    - {{// comment}}   (removed)
    """
    rng_pick: Random | None = None
    if seed:
        rng_pick = Random(seed)

    def _replace(match: re.Match[str]) -> str:
        name = (match.group(1) or "").strip()
        args = match.group(2)

        if name.startswith("//"):
            return ""

        if name in ("date", "time", "isodate"):
            now = datetime.now(timezone.utc).astimezone()
            if name == "date":
                return now.strftime("%Y-%m-%d")
            if name == "time":
                return now.strftime("%H:%M:%S")
            return now.isoformat(timespec="seconds")

        if name in ("random", "pick"):
            parts = [p.strip() for p in (args or "").split("::") if p.strip()]
            if not parts:
                return ""
            if name == "random":
                return Random().choice(parts)
            if rng_pick is None:
                return Random().choice(parts)
            return rng_pick.choice(parts)

        return match.group(0)

    return _MACRO_TOKEN_RE.sub(_replace, text)


def render_template(template: str, values: dict[str, Any], *, macro_seed: str | None = None) -> tuple[str, list[str], str | None]:
    if not template:
        return "", [], None

    escaped, mapping = _escape_macros(template)
    errors: list[str] = []
    try:
        ast = _JINJA.parse(escaped)
        declared = meta.find_undeclared_variables(ast)
    except Exception as exc:
        declared = set()
        msg = str(exc).replace("\n", " ").strip()
        if len(msg) > 200:
            msg = msg[:200] + "…"
        errors.append(f"jinja_parse_error:{type(exc).__name__}:{msg}")

    try:
        rendered = _JINJA.from_string(escaped).render(**values)
    except Exception as exc:
        # Keep M0 compatibility: rendering errors should not crash generation.
        rendered = escaped
        msg = str(exc).replace("\n", " ").strip()
        if len(msg) > 200:
            msg = msg[:200] + "…"
        errors.append(f"jinja_render_error:{type(exc).__name__}:{msg}")

    missing = sorted([v for v in declared if v and v not in values])
    restored = _restore_macros(rendered, mapping)
    final = _evaluate_macros(restored, seed=macro_seed)
    error = ";".join(errors) if errors else None
    return final, missing, error
