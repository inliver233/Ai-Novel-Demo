import { storageKey } from "./storageKeys";

export function sidebarCollapsedStorageKey(userId: string): string {
  return storageKey("sidebar_collapsed", userId);
}

