import { createContext, useContext } from "react";

export type AuthUser = {
  id: string;
  displayName: string;
  isAdmin: boolean;
};

export type AuthSession = {
  expireAt: number | null;
};

export type AuthStatus = "loading" | "authenticated" | "dev_fallback" | "unauthenticated";

export type AuthState = {
  status: AuthStatus;
  user: AuthUser | null;
  session: AuthSession | null;
};

export type AuthApi = AuthState & {
  refresh: (opts?: { silent?: boolean }) => Promise<void>;
  login: (args: { userId: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthApi | null>(null);

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
