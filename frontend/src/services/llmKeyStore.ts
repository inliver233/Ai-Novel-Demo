import { getCurrentUserId } from "./currentUser";
import { storageKey } from "./storageKeys";

import type { LLMProvider } from "../types";

export function llmKeyStorageKey(provider: LLMProvider, userId: string = getCurrentUserId()): string {
  return storageKey("llm_api_key", userId, provider);
}

export function getLlmApiKey(provider: LLMProvider): string {
  return localStorage.getItem(llmKeyStorageKey(provider)) ?? "";
}

export function setLlmApiKey(provider: LLMProvider, apiKey: string): void {
  localStorage.setItem(llmKeyStorageKey(provider), apiKey);
}

export function clearLlmApiKey(provider: LLMProvider): void {
  localStorage.removeItem(llmKeyStorageKey(provider));
}
