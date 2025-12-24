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
