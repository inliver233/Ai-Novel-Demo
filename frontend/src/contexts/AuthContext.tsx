import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, apiJson } from "../services/apiClient";
import { DEFAULT_USER_ID, clearCurrentUserId, setCurrentUserId } from "../services/currentUser";
import { AuthContext, computeNextAuthRefreshDelayMs, type AuthSession, type AuthState, type AuthUser } from "./auth";

type AuthUserApi = { id: string; display_name: string; is_admin: boolean };

function mapUser(user: AuthUserApi): AuthUser {
  return { id: user.id, displayName: user.display_name, isAdmin: Boolean(user.is_admin) };
}

function fallbackUser(): AuthUser {
  return { id: DEFAULT_USER_ID, displayName: "本地用户", isAdmin: false };
}

function devFallbackEnabled(): boolean {
  if (!import.meta.env.DEV) return false;
  const raw = String(import.meta.env.VITE_DEV_FALLBACK_ENABLED ?? "")
    .trim()
    .toLowerCase();
  return raw === "1" || raw === "true" || raw === "yes";
}

export function AuthProvider(props: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null, session: null });

  const statusRef = useRef(state.status);
  useEffect(() => {
    statusRef.current = state.status;
  }, [state.status]);

  const sessionExpireAtRef = useRef<number | null>(null);
  useEffect(() => {
    sessionExpireAtRef.current = state.status === "authenticated" ? (state.session?.expireAt ?? null) : null;
  }, [state.session?.expireAt, state.status]);

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
        if (!devFallbackEnabled()) {
          setState({ status: "unauthenticated", user: null, session: null });
          return;
        }
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

  const refreshSession = useCallback(async () => {
    try {
      const res = await apiJson<{ refreshed: boolean; session: { expire_at: number } }>("/api/auth/refresh", {
        method: "POST",
        timeoutMs: 15_000,
      });
      const expireAt = res.data.session?.expire_at ?? null;
      sessionExpireAtRef.current = expireAt;
      setState((s) => {
        if (s.status !== "authenticated") return s;
        const session: AuthSession = { expireAt };
        return { ...s, session };
      });
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      if (err?.status === 401) setState({ status: "unauthenticated", user: null, session: null });
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

  const register = useCallback(
    async ({
      userId,
      password,
      displayName,
      email,
    }: {
      userId: string;
      password: string;
      displayName?: string;
      email?: string;
    }) => {
      const res = await apiJson<{ user: AuthUserApi; session: { expire_at: number } | null }>(
        "/api/auth/local/register",
        {
          method: "POST",
          body: JSON.stringify({
            user_id: userId.trim(),
            password,
            display_name: displayName,
            email,
          }),
        },
      );
      const user = mapUser(res.data.user);
      setCurrentUserId(user.id);
      setState({ status: "authenticated", user, session: { expireAt: res.data.session?.expire_at ?? null } });
    },
    [],
  );

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
    if (typeof window === "undefined") return undefined;

    let cancelled = false;
    let timerId: number | null = null;

    const scheduleNext = () => {
      if (cancelled) return;
      if (timerId !== null) window.clearTimeout(timerId);

      const delayMs = computeNextAuthRefreshDelayMs({ expireAtSec: sessionExpireAtRef.current });
      timerId = window.setTimeout(async () => {
        await refreshSession();
        scheduleNext();
      }, delayMs);
    };

    scheduleNext();
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [refreshSession, state.status]);

  const value = useMemo(
    () => ({
      ...state,
      refresh,
      login,
      register,
      logout,
    }),
    [login, logout, refresh, register, state],
  );

  return <AuthContext.Provider value={value}>{props.children}</AuthContext.Provider>;
}
