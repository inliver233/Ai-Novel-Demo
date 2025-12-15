export const STORAGE_PREFIX = "ainovel::";

export function storageKey(...parts: Array<string | number>): string {
  const normalized = parts.map((p) => String(p).trim());
  return `${STORAGE_PREFIX}${normalized.join("::")}`;
}

export const AUTH_USER_ID_STORAGE_KEY = storageKey("auth", "user_id");
