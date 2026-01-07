from __future__ import annotations

from typing import Any


def extract_openai_like_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: list[str] = []
                    for part in content:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                    if parts:
                        return "".join(parts)
            if isinstance(first.get("text"), str):
                return first["text"]
            delta = first.get("delta")
            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                return delta["content"]

    # OpenAI Responses API (some gateways are "OpenAI-compatible" but return Responses-like shapes)
    output = data.get("output")
    if isinstance(output, list) and output:
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
        if parts:
            return "".join(parts)

    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    if isinstance(data.get("content"), str):
        return data["content"]

    return None


def extract_openai_finish_reason(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict) and isinstance(first.get("finish_reason"), str):
            return first["finish_reason"] or None
    if isinstance(data.get("finish_reason"), str):
        return data["finish_reason"] or None
    return None


def extract_openai_stream_delta_text(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("type"), str) and data.get("type") == "response.output_text.delta" and isinstance(data.get("delta"), str):
        return data["delta"]
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts: list[str] = []
                    for part in content:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and isinstance(part.get("text"), str):
                            parts.append(part["text"])
                    if parts:
                        return "".join(parts)
            if isinstance(first.get("text"), str):
                return first["text"]
    return None
