import type { LLMProvider } from "../../types";

export type LlmForm = {
  provider: LLMProvider;
  base_url: string;
  model: string;
  temperature: string;
  top_p: string;
  max_tokens: string;
  presence_penalty: string;
  frequency_penalty: string;
  top_k: string;
  stop: string;
  timeout_seconds: string;
  extra: string;
};

export type PromptForm = {
  outline_generate: { system_template: string; user_template: string };
  chapter_generate: { system_template: string; user_template: string };
};

export type TemplatePreview = {
  system: string;
  user: string;
  missing: string[];
};
