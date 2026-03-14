import { describe, expect, it } from "vitest";

import type { GenerateForm } from "../types";
import {
  AI_GENERATE_ADVANCED_MEMORY_MODULES,
  AI_GENERATE_CONTEXT_TOGGLES,
  AI_GENERATE_PRIMARY_MEMORY_MODULES,
  getAiGenerateDrawerState,
  getStyleHelperText,
} from "./aiGenerateDrawerModels";

function makeForm(overrides: Partial<GenerateForm> = {}): GenerateForm {
  return {
    instruction: "demo",
    target_word_count: 2000,
    macro_seed: "",
    prompt_override: null,
    stream: false,
    plan_first: false,
    post_edit: false,
    post_edit_sanitize: false,
    content_optimize: false,
    style_id: null,
    memory_injection_enabled: true,
    memory_query_text: "",
    memory_modules: {
      worldbook: true,
      story_memory: true,
      semantic_history: false,
      foreshadow_open_loops: false,
      structured: true,
      tables: true,
      vector_rag: true,
      graph: true,
      fractal: true,
    },
    context: {
      include_world_setting: true,
      include_style_guide: true,
      include_constraints: true,
      include_outline: true,
      include_smart_context: true,
      require_sequential: false,
      character_ids: [],
      previous_chapter: "summary",
    },
    ...overrides,
  };
}

describe("aiGenerateDrawerModels", () => {
  it("derives reliable transport warnings from advanced generation flags", () => {
    const noAdvanced = getAiGenerateDrawerState({
      genForm: makeForm({ stream: true }),
      preset: { project_id: "p1", provider: "openai", model: "gpt-test", stop: [], extra: {} },
    });
    const planFirst = getAiGenerateDrawerState({
      genForm: makeForm({ plan_first: true, stream: false }),
      preset: { project_id: "p1", provider: "openai", model: "gpt-test", stop: [], extra: {} },
    });

    expect(noAdvanced.autoReliableTransport).toBe(false);
    expect(noAdvanced.showUnsupportedStreamWarning).toBe(false);
    expect(planFirst.reliableTransportRequired).toBe(true);
    expect(planFirst.autoReliableTransport).toBe(true);
  });

  it("flags unsupported stream fallback only for non-openai presets without reliable transport", () => {
    const unsupported = getAiGenerateDrawerState({
      genForm: makeForm({ stream: true }),
      preset: { project_id: "p1", provider: "anthropic", model: "local", stop: [], extra: {} },
    });
    const withReliableTransport = getAiGenerateDrawerState({
      genForm: makeForm({ stream: true, post_edit: true }),
      preset: { project_id: "p1", provider: "anthropic", model: "local", stop: [], extra: {} },
    });

    expect(unsupported.showUnsupportedStreamWarning).toBe(true);
    expect(withReliableTransport.showUnsupportedStreamWarning).toBe(false);
  });

  it("keeps prompt override and style helper text copy stable", () => {
    const state = getAiGenerateDrawerState({
      genForm: makeForm({ prompt_override: { user: "override" } }),
      preset: null,
    });

    expect(state.hasPromptOverride).toBe(true);
    expect(state.presetSummary).toBe("未加载 LLM 配置");
    expect(getStyleHelperText("项目默认风格", null)).toBe("项目默认：项目默认风格");
    expect(getStyleHelperText(null, "E_STYLE")).toBe("项目默认：（未设置） | 加载失败：E_STYLE");
  });

  it("keeps mapped context and memory module groups deterministic", () => {
    expect(AI_GENERATE_PRIMARY_MEMORY_MODULES.map((item) => item.key)).toEqual(["worldbook", "tables"]);
    expect(AI_GENERATE_ADVANCED_MEMORY_MODULES.map((item) => item.key)).toEqual([
      "story_memory",
      "semantic_history",
      "foreshadow_open_loops",
      "structured",
      "vector_rag",
      "graph",
      "fractal",
    ]);
    expect(AI_GENERATE_CONTEXT_TOGGLES.map((item) => item.key)).toEqual([
      "include_world_setting",
      "include_style_guide",
      "include_constraints",
      "include_outline",
      "include_smart_context",
      "require_sequential",
    ]);
  });
});
