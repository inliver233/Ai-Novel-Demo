from __future__ import annotations

import re

# Only redact `?key=...` / `&key=...` in URLs. Do NOT redact generic `key=...` in prompt content
# (e.g. `<TABLES>` rows: `key=mc_level`) which is not a secret and is needed for observability.
_KEY_QS_RE = re.compile(r"(?i)([?&]key=)[^&\s\"]+")
_ANTHROPIC_KEY_RE = re.compile(r"(?i)sk-ant-[A-Za-z0-9_-]{8,}")
_OPENAI_KEY_RE = re.compile(r"(?i)sk-[A-Za-z0-9_-]{8,}")
_GOOGLE_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}\b")
_BEARER_TOKEN_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")
_X_LLM_API_KEY_RE = re.compile(r"(?i)(x-llm-api-key\s*[:=]\s*)[^\s\"']+")


def redact_text(text: str) -> str:
    if not text:
        return text
    text = _KEY_QS_RE.sub(r"\1***", text)
    text = _ANTHROPIC_KEY_RE.sub("sk-ant-***", text)
    text = _OPENAI_KEY_RE.sub("sk-***", text)
    text = _GOOGLE_KEY_RE.sub("AIza***", text)
    text = _BEARER_TOKEN_RE.sub(r"\1***", text)
    text = _X_LLM_API_KEY_RE.sub(r"\1***", text)
    return text
