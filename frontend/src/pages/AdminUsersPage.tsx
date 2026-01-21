import { useCallback, useEffect, useMemo, useState } from "react";

import { useToast } from "../components/ui/toast";
import { useAuth } from "../contexts/auth";
import { humanizeYesNo } from "../lib/humanize";
import { ApiError, apiJson } from "../services/apiClient";

type AdminUser = {
  id: string;
  email: string | null;
  display_name: string | null;
  is_admin: boolean;
  disabled: boolean;
  password_updated_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type CreateUserForm = {
  user_id: string;
  display_name: string;
  email: string;
  is_admin: boolean;
  password: string;
};

export function AdminUsersPage() {
  const auth = useAuth();
  const toast = useToast();

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [tempPasswords, setTempPasswords] = useState<Record<string, string>>({});
  const [form, setForm] = useState<CreateUserForm>({
    user_id: "",
    display_name: "",
    email: "",
    is_admin: false,
    password: "",
  });

  const canManage = auth.status === "authenticated" && Boolean(auth.user?.isAdmin);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiJson<{ users: AdminUser[] }>("/api/auth/admin/users");
      const next = Array.isArray(res.data.users) ? res.data.users : [];
      next.sort((a, b) => String(a.id ?? "").localeCompare(String(b.id ?? "")));
      setUsers(next);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (!canManage) return;
    void load();
  }, [canManage, load]);

  const createUser = useCallback(async () => {
    if (!canManage) return;
    const userId = form.user_id.trim();
    if (!userId) {
      toast.toastError("user_id 不能为空");
      return;
    }
    setSaving(true);
    try {
      const res = await apiJson<{ user: AdminUser; temp_password: string | null }>("/api/auth/admin/users", {
        method: "POST",
        body: JSON.stringify({
          user_id: userId,
          display_name: form.display_name.trim() || null,
          email: form.email.trim() || null,
          is_admin: Boolean(form.is_admin),
          password: form.password.trim() || null,
        }),
      });
      const user = res.data.user;
      if (res.data.temp_password) {
        setTempPasswords((v) => ({ ...v, [user.id]: res.data.temp_password ?? "" }));
      }
      toast.toastSuccess("用户已创建", res.request_id);
      setForm((v) => ({ ...v, user_id: "", password: "" }));
      await load();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setSaving(false);
    }
  }, [canManage, form.display_name, form.email, form.is_admin, form.password, form.user_id, load, toast]);

  const resetPassword = useCallback(
    async (targetUserId: string) => {
      if (!canManage) return;
      setSaving(true);
      try {
        const res = await apiJson<{ temp_password: string }>(`/api/auth/admin/users/${targetUserId}/password/reset`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        setTempPasswords((v) => ({ ...v, [targetUserId]: res.data.temp_password }));
        toast.toastSuccess("密码已重置（请复制一次性密码）", res.request_id);
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setSaving(false);
      }
    },
    [canManage, toast],
  );

  const setDisabled = useCallback(
    async (targetUserId: string, disabled: boolean) => {
      if (!canManage) return;
      setSaving(true);
      try {
        await apiJson<Record<string, never>>(`/api/auth/admin/users/${targetUserId}/disable`, {
          method: "POST",
          body: JSON.stringify({ disabled }),
        });
        toast.toastSuccess(disabled ? "已禁用" : "已启用");
        await load();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setSaving(false);
      }
    },
    [canManage, load, toast],
  );

  const visibleUsers = useMemo(() => users, [users]);

  if (!canManage) {
    return (
      <div className="mx-auto max-w-screen-md px-4 py-10 sm:px-6 lg:px-8">
        <div className="rounded-atelier border border-border bg-surface p-6">
          <div className="font-content text-xl text-ink">管理员用户管理</div>
          <div className="mt-2 text-sm text-subtext">
            当前账号无管理员权限（需要 authenticated admin）。如需启用，请使用 AUTH_ADMIN_* 创建管理员并登录。
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-content text-2xl text-ink">管理员用户管理</div>
          <div className="mt-1 text-xs text-subtext">创建 / 列表 / 重置密码 / 禁用（最小闭环）</div>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" disabled={loading || saving} onClick={() => void load()} type="button">
            {loading ? "加载中…" : "刷新列表"}
          </button>
        </div>
      </div>

      <section className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="text-sm font-medium text-ink">创建用户</div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="text-sm text-ink">
            <div className="text-xs text-subtext">user_id</div>
            <input
              className="mt-1 w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm"
              value={form.user_id}
              onChange={(e) => setForm((v) => ({ ...v, user_id: e.target.value }))}
            />
          </label>
          <label className="text-sm text-ink">
            <div className="text-xs text-subtext">display_name</div>
            <input
              className="mt-1 w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm"
              value={form.display_name}
              onChange={(e) => setForm((v) => ({ ...v, display_name: e.target.value }))}
            />
          </label>
          <label className="text-sm text-ink">
            <div className="text-xs text-subtext">email（可选）</div>
            <input
              className="mt-1 w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm"
              value={form.email}
              onChange={(e) => setForm((v) => ({ ...v, email: e.target.value }))}
            />
          </label>
          <label className="text-sm text-ink">
            <div className="text-xs text-subtext">password（可选，留空则生成一次性密码）</div>
            <input
              className="mt-1 w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm"
              value={form.password}
              onChange={(e) => setForm((v) => ({ ...v, password: e.target.value }))}
            />
          </label>
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={form.is_admin}
              onChange={(e) => setForm((v) => ({ ...v, is_admin: e.target.checked }))}
            />
            <span>is_admin</span>
          </label>
          <button className="btn btn-primary" disabled={saving} onClick={() => void createUser()} type="button">
            {saving ? "提交中…" : "创建"}
          </button>
        </div>
      </section>

      <section className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="text-sm font-medium text-ink">用户列表</div>
        <div className="mt-3 overflow-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs text-subtext">
              <tr>
                <th className="py-2 pr-3">id</th>
                <th className="py-2 pr-3">display_name</th>
                <th className="py-2 pr-3">is_admin</th>
                <th className="py-2 pr-3">disabled</th>
                <th className="py-2 pr-3">temp_password</th>
                <th className="py-2 pr-3">actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleUsers.map((u) => (
                <tr key={u.id} className="border-t border-border">
                  <td className="py-2 pr-3 font-mono text-xs">{u.id}</td>
                  <td className="py-2 pr-3">{u.display_name ?? "-"}</td>
                  <td className="py-2 pr-3">{humanizeYesNo(u.is_admin)}</td>
                  <td className="py-2 pr-3">{humanizeYesNo(u.disabled)}</td>
                  <td className="py-2 pr-3 font-mono text-[11px]">{tempPasswords[u.id] ?? "-"}</td>
                  <td className="py-2 pr-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={saving}
                        onClick={() => void resetPassword(u.id)}
                        type="button"
                      >
                        Reset password
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={saving}
                        onClick={() => void setDisabled(u.id, !u.disabled)}
                        type="button"
                      >
                        {u.disabled ? "Enable" : "Disable"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {visibleUsers.length === 0 ? (
                <tr>
                  <td className="py-3 text-xs text-subtext" colSpan={6}>
                    暂无数据
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
