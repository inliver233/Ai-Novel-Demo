import { AUTH_USER_ID_STORAGE_KEY } from "./storageKeys";

export const DEFAULT_USER_ID = "local-user";
export { AUTH_USER_ID_STORAGE_KEY };

export function getCurrentUserId(): string {
  return localStorage.getItem(AUTH_USER_ID_STORAGE_KEY) ?? DEFAULT_USER_ID;
}
