import type { Dispatch, RefObject, SetStateAction } from "react";

import { humanizeMemberRole } from "../../lib/humanize";
import type { Project, ProjectSettings } from "../../types";

import type { ProjectForm, ProjectMembershipItem, SettingsForm } from "./models";
import { SETTINGS_COPY } from "./settingsCopy";

type SettingsCoreSectionsProps = {
  projectForm: ProjectForm;
  setProjectForm: Dispatch<SetStateAction<ProjectForm>>;
  settingsForm: SettingsForm;
  setSettingsForm: Dispatch<SetStateAction<SettingsForm>>;
  dirty: boolean;
  saving: boolean;
  autoUpdateMasterRef: RefObject<HTMLInputElement | null>;
  autoUpdateAllEnabled: boolean;
  onSetAllAutoUpdates: (enabled: boolean) => void;
  onGoToCharacters: () => void;
  onSave: () => void;
  baselineProject: Project;
  baselineSettings: ProjectSettings;
  canManageMemberships: boolean;
  currentUserId: string;
  membershipsLoading: boolean;
  membershipSaving: boolean;
  memberships: ProjectMembershipItem[];
  inviteUserId: string;
  onChangeInviteUserId: (value: string) => void;
  inviteRole: "viewer" | "editor";
  onChangeInviteRole: (role: "viewer" | "editor") => void;
  onInviteMember: () => void;
  onLoadMemberships: () => void;
  onUpdateMemberRole: (targetUserId: string, role: "viewer" | "editor") => void;
  onRemoveMember: (targetUserId: string) => void;
};

export function SettingsCoreSections(props: SettingsCoreSectionsProps) {
  const {
    projectForm,
    setProjectForm,
    settingsForm,
    setSettingsForm,
    dirty,
    saving,
    autoUpdateMasterRef,
    autoUpdateAllEnabled,
    onSetAllAutoUpdates,
    onGoToCharacters,
    onSave,
    baselineProject,
    baselineSettings,
    canManageMemberships,
    currentUserId,
    membershipsLoading,
    membershipSaving,
    memberships,
    inviteUserId,
    onChangeInviteUserId,
    inviteRole,
    onChangeInviteRole,
    onInviteMember,
    onLoadMemberships,
    onUpdateMemberRole,
    onRemoveMember,
  } = props;
  return (
    <>
      <section className="panel p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="grid gap-2">
            <div className="font-content text-xl">项目信息</div>
            <div className="text-xs text-subtext">名称 / 题材 / 一句话梗概（logline）</div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button className="btn btn-secondary" disabled={saving} onClick={onGoToCharacters} type="button">
              {dirty ? "保存并下一步：角色卡" : "下一步：角色卡"}
            </button>
            <button className="btn btn-primary" disabled={!dirty || saving} onClick={onSave} type="button">
              保存
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 sm:col-span-1">
            <span className="text-xs text-subtext">项目名</span>
            <input
              className="input"
              name="project_name"
              value={projectForm.name}
              onChange={(e) => setProjectForm((value) => ({ ...value, name: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-1">
            <span className="text-xs text-subtext">题材</span>
            <input
              className="input"
              name="project_genre"
              value={projectForm.genre}
              onChange={(e) => setProjectForm((value) => ({ ...value, genre: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-3">
            <span className="text-xs text-subtext">一句话梗概（logline）</span>
            <textarea
              className="textarea"
              name="project_logline"
              rows={2}
              value={projectForm.logline}
              onChange={(e) => setProjectForm((value) => ({ ...value, logline: e.target.value }))}
            />
          </label>
        </div>
      </section>

      <section className="panel p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl">创作设定（必填）</div>
          <div className="text-xs text-subtext">写作/大纲生成会引用这里的内容；建议尽量具体。</div>
        </div>
        <div className="mt-4 grid gap-4">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">世界观</span>
            <textarea
              className="textarea atelier-content"
              name="world_setting"
              rows={6}
              value={settingsForm.world_setting}
              onChange={(e) => setSettingsForm((value) => ({ ...value, world_setting: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">风格</span>
            <textarea
              className="textarea atelier-content"
              name="style_guide"
              rows={6}
              value={settingsForm.style_guide}
              onChange={(e) => setSettingsForm((value) => ({ ...value, style_guide: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">约束</span>
            <textarea
              className="textarea atelier-content"
              name="constraints"
              rows={6}
              value={settingsForm.constraints}
              onChange={(e) => setSettingsForm((value) => ({ ...value, constraints: e.target.value }))}
            />
          </label>
        </div>
      </section>

      <section className="panel p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl">自动更新（推荐）</div>
          <div className="text-xs text-subtext">章节定稿（done）后自动触发后台更新任务；普通用户建议保持开启。</div>
        </div>

        <div className="mt-4 grid gap-2">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              ref={autoUpdateMasterRef}
              className="checkbox"
              checked={autoUpdateAllEnabled}
              onChange={(e) => onSetAllAutoUpdates(e.target.checked)}
              type="checkbox"
            />
            一键开关：自动更新（章节定稿后触发）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_worldbook_enabled}
              onChange={(e) =>
                setSettingsForm((value) => ({ ...value, auto_update_worldbook_enabled: e.target.checked }))
              }
              type="checkbox"
            />
            世界书：自动更新条目（worldbook_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_characters_enabled}
              onChange={(e) =>
                setSettingsForm((value) => ({ ...value, auto_update_characters_enabled: e.target.checked }))
              }
              type="checkbox"
            />
            角色卡：自动更新（characters_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_story_memory_enabled}
              onChange={(e) =>
                setSettingsForm((value) => ({ ...value, auto_update_story_memory_enabled: e.target.checked }))
              }
              type="checkbox"
            />
            剧情记忆：自动分析并写入（plot_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_graph_enabled}
              onChange={(e) => setSettingsForm((value) => ({ ...value, auto_update_graph_enabled: e.target.checked }))}
              type="checkbox"
            />
            图谱：自动更新（graph_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_vector_enabled}
              onChange={(e) => setSettingsForm((value) => ({ ...value, auto_update_vector_enabled: e.target.checked }))}
              type="checkbox"
            />
            向量索引：自动重建（vector_rebuild）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_search_enabled}
              onChange={(e) => setSettingsForm((value) => ({ ...value, auto_update_search_enabled: e.target.checked }))}
              type="checkbox"
            />
            搜索索引：自动重建（search_rebuild）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_fractal_enabled}
              onChange={(e) =>
                setSettingsForm((value) => ({ ...value, auto_update_fractal_enabled: e.target.checked }))
              }
              type="checkbox"
            />
            分形记忆：自动重建（fractal_rebuild）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_tables_enabled}
              onChange={(e) => setSettingsForm((value) => ({ ...value, auto_update_tables_enabled: e.target.checked }))}
              type="checkbox"
            />
            数值表格：自动更新（table_ai_update）
          </label>
        </div>

        <div className="mt-2 text-xs text-subtext">
          提示：关闭后不会在「章节定稿」时自动排队；仍可在对应页面/任务中心手动触发。
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="btn btn-secondary btn-sm"
            disabled={saving}
            onClick={() => onSetAllAutoUpdates(true)}
            type="button"
          >
            全部开启（推荐）
          </button>
        </div>
      </section>

      <details className="panel" aria-label="上下文优化（Context Optimizer）">
        <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
          <div className="grid gap-1">
            <div className="font-content text-xl text-ink">上下文优化（Context Optimizer）</div>
            <div className="text-xs text-subtext">
              对 StructuredMemory / WORLD_BOOK 注入做去重、排序、表格化合并，用于节省 tokens 并提升可读性（默认关闭）。
            </div>
            <div className="text-xs text-subtext">
              {SETTINGS_COPY.contextOptimizer.status(baselineSettings.context_optimizer_enabled)}
            </div>
          </div>
        </summary>

        <div className="px-6 pb-6 pt-0">
          <div className="mt-4 grid gap-2">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                checked={settingsForm.context_optimizer_enabled}
                onChange={(e) =>
                  setSettingsForm((value) => ({ ...value, context_optimizer_enabled: e.target.checked }))
                }
                type="checkbox"
              />
              启用 ContextOptimizer（影响 Prompt 预览与生成）
            </label>
            <div className="text-[11px] text-subtext">提示：写作页「上下文预览」会显示优化摘要与 diff。</div>
          </div>
        </div>
      </details>

      <details className="panel" aria-label="协作成员（Project Memberships）">
        <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
          <div className="grid gap-1">
            <div className="font-content text-xl text-ink">协作成员（Project Memberships）</div>
            <div className="text-xs text-subtext">
              项目 owner 可邀请/改角色/移除成员；非成员访问将被 404（RBAC fail-closed）。
            </div>
            <div className="text-xs text-subtext">owner: {baselineProject.owner_user_id}</div>
          </div>
        </summary>

        <div className="px-6 pb-6 pt-0">
          {canManageMemberships ? (
            <div className="mt-4 grid gap-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">邀请 user_id</span>
                  <input
                    className="input"
                    id="invite_user_id"
                    name="invite_user_id"
                    value={inviteUserId}
                    onChange={(e) => onChangeInviteUserId(e.target.value)}
                    placeholder="admin"
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">角色</span>
                  <select
                    className="select"
                    id="invite_role"
                    name="invite_role"
                    value={inviteRole}
                    onChange={(e) => onChangeInviteRole(e.target.value === "editor" ? "editor" : "viewer")}
                  >
                    <option value="viewer">{humanizeMemberRole("viewer")}</option>
                    <option value="editor">{humanizeMemberRole("editor")}</option>
                  </select>
                </label>
                <div className="flex gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={membershipSaving || membershipsLoading}
                    onClick={onInviteMember}
                    type="button"
                  >
                    邀请
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={membershipSaving || membershipsLoading}
                    onClick={onLoadMemberships}
                    type="button"
                  >
                    {membershipsLoading ? "刷新中…" : "刷新"}
                  </button>
                </div>
              </div>

              <div className="overflow-auto rounded-atelier border border-border bg-canvas">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="text-xs text-subtext">
                    <tr>
                      <th className="px-3 py-2">user_id</th>
                      <th className="px-3 py-2">display_name</th>
                      <th className="px-3 py-2">role</th>
                      <th className="px-3 py-2">actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memberships.map((membership) => {
                      const memberUserId = membership.user?.id ?? "";
                      const isOwnerRow = memberUserId === baselineProject.owner_user_id || membership.role === "owner";
                      return (
                        <tr key={memberUserId} className="border-t border-border">
                          <td className="px-3 py-2 font-mono text-xs">{memberUserId}</td>
                          <td className="px-3 py-2">{membership.user?.display_name ?? "-"}</td>
                          <td className="px-3 py-2">
                            {isOwnerRow ? (
                              <span className="text-xs text-subtext">{humanizeMemberRole("owner")}</span>
                            ) : (
                              <select
                                className="select"
                                name="member_role"
                                value={membership.role === "editor" ? "editor" : "viewer"}
                                disabled={membershipSaving || membershipsLoading}
                                onChange={(e) =>
                                  onUpdateMemberRole(memberUserId, e.target.value === "editor" ? "editor" : "viewer")
                                }
                              >
                                <option value="viewer">{humanizeMemberRole("viewer")}</option>
                                <option value="editor">{humanizeMemberRole("editor")}</option>
                              </select>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            {isOwnerRow ? (
                              <span className="text-xs text-subtext">-</span>
                            ) : (
                              <button
                                className="btn btn-secondary"
                                disabled={membershipSaving || membershipsLoading}
                                onClick={() => onRemoveMember(memberUserId)}
                                type="button"
                              >
                                移除
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {memberships.length === 0 ? (
                      <tr>
                        <td className="px-3 py-3 text-xs text-subtext" colSpan={4}>
                          暂无成员数据
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="mt-4 text-xs text-subtext">
              仅项目 owner（{baselineProject.owner_user_id}）可管理成员；当前用户：{currentUserId}。
            </div>
          )}
        </div>
      </details>
    </>
  );
}
