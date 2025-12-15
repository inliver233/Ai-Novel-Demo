import { getCurrentUserId } from "./currentUser";
import { storageKey } from "./storageKeys";

export type ThemeMode = "light" | "dark";

export type ThemeState = {
  themeId: "paper-ink";
  mode: ThemeMode;
};

export function themeStorageKey(userId: string = getCurrentUserId()): string {
  return storageKey("theme", userId);
}

export function readThemeState(): ThemeState | null {
  const raw = localStorage.getItem(themeStorageKey());
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ThemeState;
  } catch {
    return null;
  }
}

export function writeThemeState(state: ThemeState): void {
  localStorage.setItem(themeStorageKey(), JSON.stringify(state));
  applyThemeState(state);
}

export function applyThemeState(state: ThemeState): void {
  const root = document.documentElement;
  root.dataset.theme = state.themeId;
  if (state.mode === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}
