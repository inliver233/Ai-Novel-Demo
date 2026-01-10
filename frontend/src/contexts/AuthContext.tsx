import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, apiJson } from "../services/apiClient";
import { DEFAULT_USER_ID, clearCurrentUserId, setCurrentUserId } from "../services/currentUser";
import { AuthContext, type AuthSession, type AuthState, type AuthUser } from "./auth";

type AuthUserApi = { id: string; display_name: string; is_admin: boolean };

function mapUser(user: AuthUserApi): AuthUser {
  return { id: user.id, displayName: user.display_name, isAdmin: Boolean(user.is_admin) };
}

function fallbackUser(): AuthUser {
  return { id: DEFAULT_USER_ID, displayName: "本地用户", isAdmin: false };
}

export function AuthProvider(props: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null, session: null });

  const statusRef = useRef(state.status);
  useEffect(() => {
    statusRef.current = state.status;
  }, [state.status]);

  const refresh = useCallback(async ({ silent }: { silent?: boolean } = {}) => {
    if (!silent) setState((s) => ({ ...s, status: "loading" }));
    try {
      const res = await apiJson<{ user: AuthUserApi; session: { expire_at: number } | null }>("/api/auth/user", {
        timeoutMs: 15_000,
      });
      const user = mapUser(res.data.user);
      setCurrentUserId(user.id);
      setState({ status: "authenticated", user, session: { expireAt: res.data.session?.expire_at ?? null } });
      return;
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      if (err?.status === 401) {
        try {
          await apiJson<{ projects: unknown[] }>("/api/projects", { timeoutMs: 15_000 });
          setCurrentUserId(DEFAULT_USER_ID);
          setState({ status: "dev_fallback", user: fallbackUser(), session: null });
          return;
        } catch {
          setState({ status: "unauthenticated", user: null, session: null });
          return;
        }
      }
      setState({ status: "unauthenticated", user: null, session: null });
    }
  }, []);

  const login = useCallback(async ({ userId, password }: { userId: string; password: string }) => {
    const res = await apiJson<{ user: AuthUserApi; session: { expire_at: number } | null }>("/api/auth/local/login", {
      method: "POST",
      body: JSON.stringify({ user_id: userId.trim(), password }),
    });
    const user = mapUser(res.data.user);
    setCurrentUserId(user.id);
    setState({ status: "authenticated", user, session: { expireAt: res.data.session?.expire_at ?? null } });
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiJson<Record<string, never>>("/api/auth/logout", { method: "POST" });
    } catch {
      // ignore
    } finally {
      clearCurrentUserId();
      await refresh({ silent: true });
    }
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onUnauthorized = () => {
      if (statusRef.current !== "authenticated") return;
      setState({ status: "unauthenticated", user: null, session: null });
    };
    window.addEventListener("ainovel:unauthorized", onUnauthorized);
    return () => window.removeEventListener("ainovel:unauthorized", onUnauthorized);
  }, []);

  useEffect(() => {
    if (state.status !== "authenticated") return undefined;

    const refreshSession = async () => {
      try {
        const res = await apiJson<{ refreshed: boolean; session: { expire_at: number } }>("/api/auth/refresh", {
          method: "POST",
          timeoutMs: 15_000,
        });
        setState((s) => {
          if (s.status !== "authenticated") return s;
          const session: AuthSession = { expireAt: res.data.session?.expire_at ?? null };
          return { ...s, session };
        });
      } catch (e) {
        const err = e instanceof ApiError ? e : null;
        if (err?.status === 401) setState({ status: "unauthenticated", user: null, session: null });
      }
    };

    const id = window.setInterval(() => void refreshSession(), 5 * 60_000);
    return () => window.clearInterval(id);
  }, [state.status]);

  const value = useMemo(
    () => ({
      ...state,
      refresh,
      login,
      logout,
    }),
    [login, logout, refresh, state],
  );

  return <AuthContext.Provider value={value}>{props.children}</AuthContext.Provider>;
}
