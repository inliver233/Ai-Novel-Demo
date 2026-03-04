import { describe, expect, it } from "vitest";

import type { LLMPreset } from "../../types";
import { buildPresetPayload, DEFAULT_LLM_FORM, formFromPreset, payloadEquals, payloadFromPreset } from "./models";

describe("prompts/models", () => {
  it("parses responses reasoning/text verbosity from extra", () => {
    const preset: LLMPreset = {
      project_id: "p1",
      provider: "openai_responses",
      base_url: "https://api.openai.com/v1",
      model: "gpt-5-mini",
      temperature: 0.7,
      top_p: 1,
      max_tokens: 4096,
      stop: [],
      timeout_seconds: 180,
      extra: {
        reasoning: { effort: "low" },
        text: { verbosity: "high", format: { type: "json_object" } },
      },
    };
    const form = formFromPreset(preset);
    expect(form.reasoning_effort).toBe("low");
    expect(form.text_verbosity).toBe("high");
  });

  it("builds payload and preserves non-managed extra fields", () => {
    const form = {
      ...DEFAULT_LLM_FORM,
      provider: "openai_responses" as const,
      model: "gpt-5-mini",
      reasoning_effort: "medium",
      text_verbosity: "low",
      extra: JSON.stringify({
        text: { format: { type: "json_schema", name: "x", schema: { type: "object" } } },
      }),
    };
    const out = buildPresetPayload(form);
    expect(out.ok).toBe(true);
    if (!out.ok) return;
    expect(out.payload.extra.reasoning).toEqual({ effort: "medium" });
    expect(out.payload.extra.text).toEqual({
      format: { type: "json_schema", name: "x", schema: { type: "object" } },
      verbosity: "low",
    });
  });

  it("rejects invalid anthropic thinking budget", () => {
    const form = {
      ...DEFAULT_LLM_FORM,
      provider: "anthropic" as const,
      model: "claude-3-7-sonnet-20250219",
      anthropic_thinking_enabled: true,
      anthropic_thinking_budget_tokens: "abc",
    };
    const out = buildPresetPayload(form);
    expect(out.ok).toBe(false);
  });

  it("payload roundtrip remains equal", () => {
    const preset: LLMPreset = {
      project_id: "p1",
      provider: "gemini",
      base_url: "https://generativelanguage.googleapis.com",
      model: "gemini-2.5-pro",
      temperature: 0.2,
      top_p: 0.8,
      max_tokens: 2048,
      top_k: 40,
      stop: ["###"],
      timeout_seconds: 120,
      extra: {
        thinkingConfig: { thinkingBudget: 512, includeThoughts: true },
      },
    };
    const payloadA = payloadFromPreset(preset);
    const form = formFromPreset(preset);
    const payloadB = buildPresetPayload(form);
    expect(payloadB.ok).toBe(true);
    if (!payloadB.ok) return;
    expect(payloadEquals(payloadA, payloadB.payload)).toBe(true);
  });
});
