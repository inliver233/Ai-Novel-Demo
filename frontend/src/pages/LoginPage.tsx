import { useMemo, useState } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../contexts/auth";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError } from "../services/apiClient";
import { DEFAULT_USER_ID, getCurrentUserId } from "../services/currentUser";
import { useToast } from "../components/ui/toast";

function safeNextPath(value: string | null): string {
  if (!value) return "/";
  if (!value.startsWith("/")) return "/";
  if (value.startsWith("//")) return "/";
  return value;
}

export function LoginPage() {
  const auth = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const nextPath = useMemo(() => safeNextPath(searchParams.get("next")), [searchParams]);

  const [form, setForm] = useState(() => ({
    userId: getCurrentUserId() === DEFAULT_USER_ID ? "" : getCurrentUserId(),
    password: "",
  }));
  const [busy, setBusy] = useState(false);

  if (auth.status === "authenticated") {
    return <Navigate to={nextPath} replace />;
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div className="mx-auto flex min-h-screen max-w-screen-sm items-center px-4 py-12">
        <div className="w-full">
          <div className="surface p-6 sm:p-8">
            <div className="font-content text-2xl text-ink">{UI_COPY.auth.loginTitle}</div>
            <div className="mt-1 text-sm text-subtext">{UI_COPY.auth.loginSubtitle}</div>

            {auth.status === "dev_fallback" ? (
              <div className="mt-4 rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
                <div className="text-ink">{UI_COPY.auth.devFallbackHint}</div>
                <div className="mt-1">{UI_COPY.auth.devFallbackRiskHint}</div>
                <div className="mt-1">{UI_COPY.auth.devFallbackNextStepHint}</div>
                <button
                  className="ui-focus-ring mt-2 inline-flex underline underline-offset-2"
                  onClick={() => navigate("/", { replace: true })}
                  type="button"
                >
                  {UI_COPY.auth.continueInDevFallback}
                </button>
              </div>
            ) : null}

            <div className="mt-6 grid gap-3">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">{UI_COPY.auth.userIdLabel}</span>
                <input
                  className="input"
                  name="user_id"
                  value={form.userId}
                  onChange={(e) => setForm((v) => ({ ...v, userId: e.target.value }))}
                  autoComplete="username"
                  placeholder={UI_COPY.auth.userIdPlaceholder}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">{UI_COPY.auth.passwordLabel}</span>
                <input
                  className="input"
                  name="password"
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm((v) => ({ ...v, password: e.target.value }))}
                  autoComplete="current-password"
                  placeholder={UI_COPY.auth.passwordPlaceholder}
                />
              </label>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setForm({ userId: "", password: "" });
                }}
                type="button"
              >
                {UI_COPY.auth.reset}
              </button>
              <button
                className="btn btn-primary"
                disabled={busy || !form.userId.trim() || !form.password}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await auth.login({ userId: form.userId.trim(), password: form.password });
                    toast.toastSuccess(UI_COPY.auth.loginSuccess);
                    navigate(nextPath, { replace: true });
                  } catch (e) {
                    const err = e as ApiError;
                    toast.toastError(`${err.message} (${err.code})`, err.requestId);
                  } finally {
                    setBusy(false);
                  }
                }}
                type="button"
              >
                {busy ? UI_COPY.auth.loggingIn : UI_COPY.auth.login}
              </button>
            </div>
          </div>
          <div className="mt-4 text-center text-xs text-subtext">{UI_COPY.auth.loginFooterHint}</div>
        </div>
      </div>
    </div>
  );
}
