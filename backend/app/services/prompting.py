from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from random import Random
from typing import Any

_MACRO_TOKEN_RE = re.compile(r"{{\s*(//[^\n]*|[a-zA-Z0-9_]+)(?:::(.*?))?\s*}}", flags=re.DOTALL)

_ESCAPE_MACRO_RE = re.compile(
    r"{{\s*(//[^\n]*|random::.*?|pick::.*?|date|time|isodate)\s*}}",
    flags=re.DOTALL,
)

_TEMPLATE_TOKEN_RE = re.compile(r"({{.*?}}|{%-?.*?-?%})", flags=re.DOTALL)

_SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")


class TemplateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _IfFrame:
    active_before: bool
    condition_true: bool
    in_else: bool = False


def _truncate_error_message(msg: str, *, limit: int = 200) -> str:
    s = msg.replace("\n", " ").strip()
    if len(s) <= limit:
        return s
    return s[:limit] + "..."


def _is_safe_path(path: str) -> bool:
    if not path or not _SAFE_PATH_RE.fullmatch(path):
        return False
    for part in path.split("."):
        if not part:
            return False
        if part.startswith("_"):
            return False
        if part.isdigit():
            continue
        if not _SAFE_NAME_RE.fullmatch(part):
            return False
    return True


def _try_resolve_path(values: dict[str, Any], path: str) -> tuple[bool, Any]:
    cur: Any = values
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return False, None
            cur = cur.get(part)
            continue
        if isinstance(cur, list) and part.isdigit():
            idx = int(part)
            if idx < 0 or idx >= len(cur):
                return False, None
            cur = cur[idx]
            continue
        return False, None
    return True, cur


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


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


_EXPR_TOKEN_RE = re.compile(
    r"""
    \s*
    (?:
        (?P<string>
            '(?:[^'\\]|\\.)*'
            |
            "(?:[^"\\]|\\.)*"
        )
        | (?P<op>==|!=|\(|\))
        | (?P<word>[A-Za-z0-9_.]+)
    )
    """,
    flags=re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class _ExprToken:
    kind: str
    value: str


def _tokenize_expr(expr: str) -> list[_ExprToken]:
    tokens: list[_ExprToken] = []
    pos = 0
    while pos < len(expr):
        m = _EXPR_TOKEN_RE.match(expr, pos)
        if m is None:
            snippet = expr[pos : min(pos + 40, len(expr))].strip()
            raise TemplateError(f"invalid_expr_syntax:{snippet}")
        pos = m.end()
        if m.group("string") is not None:
            tokens.append(_ExprToken("string", m.group("string")))
            continue
        if m.group("op") is not None:
            tokens.append(_ExprToken("op", m.group("op")))
            continue
        word = m.group("word") or ""
        if word in ("and", "or", "not", "in"):
            tokens.append(_ExprToken("kw", word))
        else:
            tokens.append(_ExprToken("ident", word))
    return tokens


class _ExprParser:
    def __init__(self, tokens: list[_ExprToken], *, values: dict[str, Any], used_vars: set[str], missing: set[str]):
        self._tokens = tokens
        self._i = 0
        self._values = values
        self._used_vars = used_vars
        self._missing = missing

    def _peek(self) -> _ExprToken | None:
        if self._i >= len(self._tokens):
            return None
        return self._tokens[self._i]

    def _eat(self) -> _ExprToken:
        tok = self._peek()
        if tok is None:
            raise TemplateError("unexpected_eof")
        self._i += 1
        return tok

    def _eat_kw(self, kw: str) -> bool:
        tok = self._peek()
        if tok is None or tok.kind != "kw" or tok.value != kw:
            return False
        self._i += 1
        return True

    def _eat_op(self, op: str) -> bool:
        tok = self._peek()
        if tok is None or tok.kind != "op" or tok.value != op:
            return False
        self._i += 1
        return True

    def parse(self) -> Any:
        value = self._parse_or()
        if self._peek() is not None:
            raise TemplateError("unexpected_token")
        return value

    def _parse_or(self) -> Any:
        left = self._parse_and()
        while self._eat_kw("or"):
            right = self._parse_and()
            left = bool(left) or bool(right)
        return left

    def _parse_and(self) -> Any:
        left = self._parse_not()
        while self._eat_kw("and"):
            right = self._parse_not()
            left = bool(left) and bool(right)
        return left

    def _parse_not(self) -> Any:
        if self._eat_kw("not"):
            return not bool(self._parse_not())
        return self._parse_compare()

    def _parse_compare(self) -> Any:
        left = self._parse_term()

        if self._eat_kw("in"):
            right = self._parse_term()
            try:
                return left in right  # type: ignore[operator]
            except Exception:
                return False

        if self._eat_op("=="):
            right = self._parse_term()
            return left == right

        if self._eat_op("!="):
            right = self._parse_term()
            return left != right

        return left

    def _parse_term(self) -> Any:
        if self._eat_op("("):
            value = self._parse_or()
            if not self._eat_op(")"):
                raise TemplateError("missing_closing_paren")
            return value

        tok = self._eat()
        if tok.kind == "string":
            try:
                v = ast.literal_eval(tok.value)
            except Exception as exc:
                raise TemplateError("invalid_string_literal") from exc
            if not isinstance(v, str):
                raise TemplateError("string_literal_not_str")
            return v

        if tok.kind == "ident":
            if not _is_safe_path(tok.value):
                raise TemplateError(f"unsafe_identifier:{tok.value}")
            self._used_vars.add(tok.value)
            ok, v = _try_resolve_path(self._values, tok.value)
            if not ok:
                self._missing.add(tok.value)
                return ""
            return v

        raise TemplateError(f"unexpected_token:{tok.kind}")


def _render_safe_template(template: str, values: dict[str, Any]) -> tuple[str, set[str], set[str]]:
    used_vars: set[str] = set()
    missing: set[str] = set()
    out: list[str] = []
    frames: list[_IfFrame] = []
    active = True

    pos = 0
    for m in _TEMPLATE_TOKEN_RE.finditer(template):
        literal = template[pos : m.start()]
        if active and literal:
            out.append(literal)
        pos = m.end()

        token = m.group(0)
        if token.startswith("{{"):
            expr = token[2:-2].strip().strip("-").strip()
            if not active:
                if _is_safe_path(expr):
                    used_vars.add(expr)
                continue
            if not _is_safe_path(expr):
                # Keep unsupported expressions as-is (but never evaluate).
                out.append(token)
                continue
            used_vars.add(expr)
            ok, v = _try_resolve_path(values, expr)
            if not ok:
                missing.add(expr)
                out.append("")
                continue
            out.append(_stringify_value(v))
            continue

        stmt = token[2:-2].strip().strip("-").strip()
        if stmt.startswith("if "):
            expr = stmt[3:].strip()
            parser = _ExprParser(_tokenize_expr(expr), values=values, used_vars=used_vars, missing=missing)
            frames.append(_IfFrame(active_before=active, condition_true=bool(parser.parse()), in_else=False))
            active = active and frames[-1].condition_true
            continue

        if stmt == "else":
            if not frames:
                raise TemplateError("unexpected_else")
            top = frames[-1]
            if top.in_else:
                raise TemplateError("duplicate_else")
            frames[-1] = _IfFrame(active_before=top.active_before, condition_true=top.condition_true, in_else=True)
            active = top.active_before and (not top.condition_true)
            continue

        if stmt == "endif":
            if not frames:
                raise TemplateError("unexpected_endif")
            top = frames.pop()
            active = top.active_before
            continue

        raise TemplateError(f"unsupported_statement:{stmt}")

    tail = template[pos:]
    if active and tail:
        out.append(tail)

    if frames:
        raise TemplateError("unclosed_if")

    return "".join(out), used_vars, missing


def render_template(template: str, values: dict[str, Any], *, macro_seed: str | None = None) -> tuple[str, list[str], str | None]:
    if not template:
        return "", [], None

    escaped, mapping = _escape_macros(template)
    errors: list[str] = []

    try:
        rendered, _, missing_vars = _render_safe_template(escaped, values)
    except Exception as exc:
        # Keep M0 compatibility: template errors should not crash generation.
        rendered = escaped
        msg = _truncate_error_message(str(exc))
        errors.append(f"template_render_error:{type(exc).__name__}:{msg}")
        missing_vars = set()

    missing = sorted(missing_vars)
    restored = _restore_macros(rendered, mapping)
    final = _evaluate_macros(restored, seed=macro_seed)
    error = ";".join(errors) if errors else None
    return final, missing, error
