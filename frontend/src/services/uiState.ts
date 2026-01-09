import { storageKey } from "./storageKeys";

export function sidebarCollapsedStorageKey(userId: string): string {
  return storageKey("sidebar_collapsed", userId);
}

export function wizardBarCollapsedStorageKey(userId: string): string {
  return storageKey("wizard_bar_collapsed", userId);
}

export function writingMemoryInjectionEnabledStorageKey(userId: string, projectId: string): string {
  return storageKey("writing", "memory_injection_enabled", userId, projectId);
}
