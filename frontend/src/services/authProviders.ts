import { apiJson } from "./apiClient";

export type AuthProviders = {
  local: { enabled: boolean };
  linuxdo: { enabled: boolean };
};

export async function fetchAuthProviders(): Promise<AuthProviders> {
  const res = await apiJson<AuthProviders>("/api/auth/providers", { timeoutMs: 15_000 });
  return res.data;
}
