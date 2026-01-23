import clsx from "clsx";
import { LayoutGroup, motion, useReducedMotion } from "framer-motion";
import { useMemo, useRef, useState } from "react";

import { transition } from "../../lib/motion";
import type { PromptPreset } from "../../types";
import type { PromptStudioTask } from "./types";

export function PromptStudioPresetListPanel(props: {
  busy: boolean;
  importBusy: boolean;
  bulkBusy: boolean;
  tasks: PromptStudioTask[];
  presets: PromptPreset[];
  selectedPresetId: string | null;
  setSelectedPresetId: (id: string | null) => void;
  createPreset: (name: string) => Promise<boolean>;
  exportPreset: () => Promise<void>;
  exportAllPresets: () => Promise<void>;
  importPreset: (file: File) => Promise<void>;
  importAllPresets: (file: File) => Promise<void>;
}) {
  const {
    busy,
    bulkBusy,
    createPreset,
    exportAllPresets,
    exportPreset,
    importAllPresets,
    importBusy,
    importPreset,
    presets,
    tasks,
    selectedPresetId,
    setSelectedPresetId,
  } = props;

  const reduceMotion = useReducedMotion();

  const [newPresetName, setNewPresetName] = useState("");
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const importAllInputRef = useRef<HTMLInputElement | null>(null);

  const [categoryFilter, setCategoryFilter] = useState<string>("__all__");

  const taskLabelByKey = useMemo(() => new Map(tasks.map((t) => [t.key, t.label])), [tasks]);

  const presetCategoryGroups = useMemo(() => {
    const groups = new Map<string, PromptPreset[]>();
    for (const p of presets) {
      const key = String(p.category ?? "").trim() || "（未分类）";
      const list = groups.get(key) ?? [];
      list.push(p);
      groups.set(key, list);
    }
    const ordered = [...groups.entries()];
    ordered.sort((a, b) => a[0].localeCompare(b[0]));
    return ordered;
  }, [presets]);

  const effectiveCategoryFilter =
    categoryFilter === "__all__" || presetCategoryGroups.some(([key]) => key === categoryFilter)
      ? categoryFilter
      : "__all__";

  const visiblePresetCategoryGroups = useMemo(() => {
    if (effectiveCategoryFilter === "__all__") return presetCategoryGroups;
    return presetCategoryGroups.filter(([key]) => key === effectiveCategoryFilter);
  }, [effectiveCategoryFilter, presetCategoryGroups]);

  const showCategoryHeaders = effectiveCategoryFilter === "__all__";

  return (
    <div className="panel p-4">
      <div className="mb-3 text-sm font-semibold">预设列表</div>
      <div className="grid gap-2">
        <div className="text-xs text-subtext">新建预设</div>
        <div className="flex gap-2">
          <input
            className="input"
            placeholder="新预设名称"
            value={newPresetName}
            onChange={(e) => setNewPresetName(e.target.value)}
            disabled={busy}
          />
          <button
            className="btn btn-secondary"
            onClick={() => {
              void (async () => {
                const ok = await createPreset(newPresetName);
                if (ok) setNewPresetName("");
              })();
            }}
            disabled={busy}
          >
            新建
          </button>
        </div>

        <div className="text-xs text-subtext">导入/导出（当前预设）</div>
        <div className="flex gap-2">
          <input
            ref={importInputRef}
            type="file"
            accept="application/json"
            className="hidden"
            data-testid="prompt-studio-import-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importPreset(file);
              if (importInputRef.current) importInputRef.current.value = "";
            }}
          />
          <input
            ref={importAllInputRef}
            type="file"
            accept="application/json"
            className="hidden"
            data-testid="prompt-studio-import-all-file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importAllPresets(file);
              if (importAllInputRef.current) importAllInputRef.current.value = "";
            }}
          />
          <button
            className="btn btn-secondary w-full"
            onClick={() => importInputRef.current?.click()}
            disabled={importBusy || busy}
          >
            导入
          </button>
          <button
            className="btn btn-secondary w-full"
            onClick={() => void exportPreset()}
            disabled={busy || !selectedPresetId}
          >
            导出
          </button>
        </div>

        <div className="text-xs text-subtext">导入/导出（整套）</div>
        <div className="flex gap-2">
          <button
            className="btn btn-secondary w-full"
            onClick={() => importAllInputRef.current?.click()}
            disabled={bulkBusy || importBusy || busy}
            type="button"
          >
            导入整套
          </button>
          <button
            className="btn btn-secondary w-full"
            onClick={() => void exportAllPresets()}
            disabled={bulkBusy || busy}
            type="button"
          >
            导出整套
          </button>
        </div>

        <div className="grid gap-1">
          <div className="text-xs text-subtext">分类</div>
          <select
            className="select"
            value={effectiveCategoryFilter}
            onChange={(e) => setCategoryFilter(e.currentTarget.value)}
            disabled={busy || bulkBusy}
          >
            <option value="__all__">全部分类</option>
            {presetCategoryGroups.map(([key]) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </div>

        <LayoutGroup id="promptstudio-presets">
          <div className="mt-2 grid gap-3">
            {visiblePresetCategoryGroups.length ? (
              visiblePresetCategoryGroups.map(([category, items]) => (
                <div key={category}>
                  {showCategoryHeaders ? <div className="text-xs text-subtext">{category}</div> : null}
                  <div className={clsx("grid gap-1", showCategoryHeaders ? "mt-1" : null)}>
                    {items.map((p) => {
                      const active = p.id === selectedPresetId;
                      const activeFor = (p.active_for ?? [])
                        .map((key) => taskLabelByKey.get(key) ?? key)
                        .filter((v) => typeof v === "string" && v.trim())
                        .join(", ");
                      return (
                        <button
                          key={p.id}
                          className={clsx(
                            "ui-focus-ring ui-transition-fast group relative w-full overflow-hidden rounded-atelier border px-3 py-2 text-left text-sm motion-safe:active:scale-[0.99]",
                            active
                              ? "border-accent/40 text-ink"
                              : "border-border text-subtext hover:bg-canvas hover:text-ink",
                          )}
                          onClick={() => setSelectedPresetId(p.id)}
                          type="button"
                        >
                          {active ? (
                            <motion.span
                              layoutId="promptstudio-preset-active"
                              className="absolute inset-0 rounded-atelier bg-canvas"
                              transition={reduceMotion ? { duration: 0.01 } : transition.fast}
                            />
                          ) : null}
                          <div className="relative z-10 truncate">{p.name}</div>
                          <div className="relative z-10 mt-1 text-xs opacity-80">{activeFor || "—"}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-xs text-subtext">暂无预设</div>
            )}
          </div>
        </LayoutGroup>

        <div className="mt-2 text-xs text-subtext">拖拽块可调整排序；预览走后端渲染。</div>
      </div>
    </div>
  );
}
