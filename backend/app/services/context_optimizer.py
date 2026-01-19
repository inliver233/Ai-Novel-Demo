from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.services.prompt_budget import estimate_tokens


_RE_TABLE_SEP = re.compile(r"\n\s*\n---\s*\n\s*\n")


def _md_escape_cell(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = value.replace("|", "\\|")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\n", "<br>")
    return value


def _wrap_tag(tag: str, inner: str) -> str:
    body = (inner or "").strip()
    if not body:
        return ""
    return f"<{tag}>\n{body}\n</{tag}>"


def _extract_tag_inner(text: str, tag: str) -> str | None:
    raw = str(text or "")
    m = re.search(rf"<{re.escape(tag)}>\n(?P<inner>.*)\n</{re.escape(tag)}>", raw, flags=re.DOTALL)
    if not m:
        return None
    return str(m.group("inner") or "").strip()


def _build_md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines = [head, sep]
    for row in rows:
        padded = (row + [""] * len(headers))[: len(headers)]
        lines.append("| " + " | ".join(_md_escape_cell(c) for c in padded) + " |")
    return "\n".join(lines).rstrip()


def _optimize_structured_memory(text: str) -> tuple[str, dict[str, Any]]:
    tag = "StructuredMemory"
    inner = _extract_tag_inner(text, tag)
    if inner is None:
        return text, {"changed": False, "reason": "tag_not_found"}

    sections: list[tuple[str, list[str]]] = []
    cur_title: str | None = None
    cur_lines: list[str] = []
    for line in inner.splitlines():
        if line.startswith("## "):
            if cur_title is not None:
                sections.append((cur_title, cur_lines))
            cur_title = line[3:].strip()
            cur_lines = []
            continue
        cur_lines.append(line)
    if cur_title is not None:
        sections.append((cur_title, cur_lines))

    if not sections:
        return text, {"changed": False, "reason": "no_sections"}

    changed = False
    out_sections: list[str] = []
    details: dict[str, Any] = {"changed": False, "sections": []}

    for title, lines in sections:
        raw_items = [ln.strip()[2:].strip() for ln in lines if ln.strip().startswith("- ")]
        if not raw_items:
            out_sections.append("## " + title)
            out_sections.extend([ln.rstrip() for ln in lines if str(ln or "").strip()])
            continue

        rows: list[list[str]] = []
        if title.lower() == "entities":
            seen: set[tuple[str, str]] = set()
            for it in raw_items:
                m = re.match(r"^\[(?P<type>[^\]]+)\]\s+(?P<rest>.*)$", it)
                entity_type = str(m.group("type")).strip() if m else ""
                rest = str(m.group("rest") if m else it).strip()
                name, sep, summary = rest.partition(":")
                name = name.strip()
                summary = summary.strip() if sep else ""
                if not name:
                    continue
                key = (entity_type.lower(), name.lower())
                if key in seen:
                    continue
                seen.add(key)
                rows.append([entity_type or "generic", name, summary])
            rows.sort(key=lambda r: (str(r[0]).lower(), str(r[1]).lower()))
            table = _build_md_table(["Type", "Name", "Summary"], rows)
        elif title.lower() == "relations":
            seen: set[tuple[str, str, str]] = set()
            for it in raw_items:
                m = re.match(
                    r"^(?P<from>.*?)\s+--\((?P<rel>.*?)\)-->\s+(?P<to>.*?)(?::\s*(?P<desc>.*))?$",
                    it,
                )
                if not m:
                    continue
                from_name = str(m.group("from") or "").strip()
                rel = str(m.group("rel") or "").strip()
                to_name = str(m.group("to") or "").strip()
                desc = str(m.group("desc") or "").strip()
                if not from_name or not to_name or not rel:
                    continue
                key = (from_name.lower(), rel.lower(), to_name.lower())
                if key in seen:
                    continue
                seen.add(key)
                rows.append([from_name, rel, to_name, desc])
            rows.sort(key=lambda r: (str(r[0]).lower(), str(r[1]).lower(), str(r[2]).lower()))
            table = _build_md_table(["From", "Relation", "To", "Desc"], rows)
        elif title.lower() == "events":
            seen: set[str] = set()
            for it in raw_items:
                name, sep, content = it.partition(":")
                name = name.strip()
                content = content.strip() if sep else ""
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                rows.append([name, content])
            rows.sort(key=lambda r: str(r[0]).lower())
            table = _build_md_table(["Title", "Content"], rows)
        elif title.lower() == "foreshadows":
            seen: set[tuple[bool, str]] = set()
            for it in raw_items:
                resolved = False
                rest = it
                if rest.startswith("[resolved]"):
                    resolved = True
                    rest = rest[len("[resolved]") :].strip()
                name, sep, content = rest.partition(":")
                name = name.strip()
                content = content.strip() if sep else ""
                if not name:
                    continue
                key = (resolved, name.lower())
                if key in seen:
                    continue
                seen.add(key)
                rows.append(["yes" if resolved else "no", name, content])
            rows.sort(key=lambda r: (r[0] != "yes", str(r[1]).lower()))
            table = _build_md_table(["Resolved", "Title", "Content"], rows)
        else:
            table = ""

        if not table:
            out_sections.append("## " + title)
            out_sections.extend([ln.rstrip() for ln in lines if str(ln or "").strip()])
            continue

        changed = True
        out_sections.append("## " + title)
        out_sections.append(table)
        details["sections"].append({"section": title, "items_in": len(raw_items), "rows_out": len(rows)})

    new_text = _wrap_tag(tag, "\n\n".join([s for s in out_sections if str(s or "").strip()]))
    if new_text and new_text != text:
        details["changed"] = changed
        return new_text, details
    return text, {"changed": False, "reason": "no_change"}


_WB_HEADER_RE = re.compile(
    r"^【世界书条目：(?P<title>.*?)\s*\|\s*(?P<reason>.*?)\s*\|\s*priority:(?P<priority>.*?)】$"
)


def _priority_rank(value: str) -> int:
    v = str(value or "").strip().lower()
    if v == "must":
        return 3
    if v == "important":
        return 2
    if v == "optional":
        return 1
    return 0


def _optimize_worldbook(text: str) -> tuple[str, dict[str, Any]]:
    tag = "WORLD_BOOK"
    inner = _extract_tag_inner(text, tag)
    if inner is None:
        return text, {"changed": False, "reason": "tag_not_found"}

    entries_raw = [p.strip() for p in _RE_TABLE_SEP.split(inner) if p and p.strip()]
    if not entries_raw:
        return text, {"changed": False, "reason": "empty"}

    rows: list[list[str]] = []
    seen: set[str] = set()
    parsed = 0
    for part in entries_raw:
        lines = [ln.rstrip() for ln in part.splitlines() if ln is not None]
        if not lines:
            continue
        header = lines[0].strip()
        content = "\n".join([ln for ln in lines[1:] if str(ln or "").strip()]).strip()
        m = _WB_HEADER_RE.match(header)
        if not m:
            title = header[:80] or "Untitled"
            reason = "unknown"
            priority = "important"
        else:
            parsed += 1
            title = str(m.group("title") or "").strip() or "Untitled"
            reason = str(m.group("reason") or "").strip() or "unknown"
            priority = str(m.group("priority") or "").strip() or "important"

        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append([title, reason, priority, content])

    rows.sort(key=lambda r: (-_priority_rank(str(r[2])), str(r[0]).lower(), str(r[1]).lower()))
    table = _build_md_table(["Title", "Reason", "Priority", "Content"], rows)
    if not table:
        return text, {"changed": False, "reason": "no_rows"}

    new_text = _wrap_tag(tag, table)
    if not new_text or new_text == text:
        return text, {"changed": False, "reason": "no_change"}

    return (
        new_text,
        {
            "changed": True,
            "entries_in": len(entries_raw),
            "entries_parsed": parsed,
            "rows_out": len(rows),
        },
    )


@dataclass(frozen=True, slots=True)
class ContextOptimizer:
    enabled: bool

    def optimize_prompt_block_states(self, block_states: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        blocks_log: list[dict[str, Any]] = []
        saved_tokens = 0

        for s in block_states:
            identifier = str(s.get("identifier") or "")
            text_after = str(s.get("text_after") or "")
            if not text_after.strip():
                continue

            before_tokens = int(s.get("tokens_after") or estimate_tokens(text_after))
            before_chars = len(text_after)
            next_text = text_after
            details: dict[str, Any] = {"changed": False}

            if identifier == "sys.memory.structured":
                next_text, details = _optimize_structured_memory(text_after)
            elif identifier == "sys.memory.worldbook":
                next_text, details = _optimize_worldbook(text_after)

            if next_text != text_after:
                s["text_after"] = next_text
                s["tokens_after"] = estimate_tokens(next_text)
                s["trimmed"] = False
                s["reason"] = (str(s.get("reason") or "") + ";" if s.get("reason") else "") + "context_optimized"

            after_tokens = int(s.get("tokens_after") or estimate_tokens(str(s.get("text_after") or "")))
            after_chars = len(str(s.get("text_after") or ""))
            saved_tokens += max(0, before_tokens - after_tokens)

            blocks_log.append(
                {
                    "identifier": identifier,
                    "changed": bool(details.get("changed")) or (next_text != text_after),
                    "before_tokens": before_tokens,
                    "after_tokens": after_tokens,
                    "before_chars": before_chars,
                    "after_chars": after_chars,
                    "details": details,
                }
            )

        return {
            "enabled": True,
            "saved_tokens_estimate": int(saved_tokens),
            "blocks": blocks_log,
        }

