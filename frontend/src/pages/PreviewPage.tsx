import clsx from "clsx";
import { BookOpen, ChevronLeft, Edit3, List } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useNavigate, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { useProjectData } from "../hooks/useProjectData";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { apiJson } from "../services/apiClient";
import { markWizardPreviewSeen } from "../services/wizard";
import type { Chapter } from "../types";

type PreviewLoaded = { chapters: Chapter[] };

const EMPTY_CHAPTERS: Chapter[] = [];

export function PreviewPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { bumpLocal, loading: wizardLoading, progress: wizardProgress } = useWizardProgress(projectId);

  const [activeId, setActiveId] = useState<string | null>(null);
  const [mobileListOpen, setMobileListOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    markWizardPreviewSeen(projectId);
    bumpLocal();
  }, [bumpLocal, projectId]);

  const previewQuery = useProjectData<PreviewLoaded>(projectId, async (id) => {
    const res = await apiJson<{ chapters: Chapter[] }>(`/api/projects/${id}/chapters`);
    return { chapters: res.data.chapters };
  });

  const chapters = previewQuery.data?.chapters ?? EMPTY_CHAPTERS;

  const effectiveActiveId = useMemo(() => {
    if (activeId && chapters.some((c) => c.id === activeId)) return activeId;
    return chapters[0]?.id ?? null;
  }, [activeId, chapters]);

  const activeChapter = useMemo(
    () => chapters.find((c) => c.id === effectiveActiveId) ?? null,
    [effectiveActiveId, chapters],
  );

  const openEditor = (chapterId: string) => {
    if (!projectId) return;
    navigate(`/projects/${projectId}/writing?chapterId=${encodeURIComponent(chapterId)}`);
  };

  const list = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="inline-flex items-center gap-2 text-sm text-ink">
          <BookOpen size={16} />
          章节
        </div>
      </div>

      <div className="flex-1 overflow-auto p-2">
        {chapters.length === 0 ? <div className="p-3 text-sm text-subtext">暂无章节</div> : null}
        <div className="grid gap-1">
          {chapters.map((c) => {
            const isActive = c.id === effectiveActiveId;
            return (
              <button
                key={c.id}
                className={clsx(
                  "flex w-full items-center justify-between gap-2 rounded-atelier border px-3 py-2 text-left text-sm",
                  isActive ? "border-accent/40 bg-accent/10 text-ink" : "border-border bg-canvas text-subtext hover:bg-surface",
                )}
                onClick={() => {
                  setActiveId(c.id);
                  setMobileListOpen(false);
                }}
                type="button"
              >
                <span className="min-w-0 truncate">
                  {c.number}. {c.title?.trim() ? c.title : "（未命名）"}
                </span>
                <span className="shrink-0 text-[11px] text-subtext">{c.status}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );

  if (previewQuery.loading) return <div className="text-subtext">加载中...</div>;

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-2">
        <button
          className="inline-flex items-center gap-2 rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas lg:hidden"
          onClick={() => setMobileListOpen(true)}
          type="button"
        >
          <List size={16} />
          章节列表
        </button>
        <button
          className="hidden items-center gap-2 rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas lg:inline-flex"
          onClick={() => setCollapsed((v) => !v)}
          type="button"
        >
          <List size={16} />
          {collapsed ? "显示章节列表" : "隐藏章节列表"}
        </button>

        <div className="min-w-0 truncate text-xs text-subtext">
          {activeChapter ? `正在预览：第 ${activeChapter.number} 章` : "请选择章节"}
        </div>

        {activeChapter ? (
          <button
            className="inline-flex items-center gap-2 rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
            onClick={() => openEditor(activeChapter.id)}
            type="button"
          >
            <Edit3 size={16} />
            编辑
          </button>
        ) : null}
      </div>

      <div className="flex gap-4">
        {!collapsed ? (
          <aside className="hidden w-[280px] shrink-0 lg:block">
            <div className="h-[calc(100vh-260px)] min-h-[520px] overflow-hidden rounded-atelier border border-border bg-surface">
              {list}
            </div>
          </aside>
        ) : null}

        <section className="min-w-0 flex-1">
          <div className="rounded-atelier border border-border bg-surface p-6">
            {activeChapter ? (
              <>
                <div className="mb-4">
                  <div className="font-content text-2xl text-ink">
                    第 {activeChapter.number} 章{activeChapter.title?.trim() ? ` · ${activeChapter.title}` : ""}
                  </div>
                  {activeChapter.status !== "done" ? (
                    <div className="mt-1 text-xs text-subtext">提示：本章状态为 {activeChapter.status}，向导会以 done 作为“写完”判定。</div>
                  ) : null}
                </div>
                <div className="atelier-content max-w-none text-ink">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{activeChapter.content_md || "_（空）_"}</ReactMarkdown>
                </div>
              </>
            ) : (
              <div className="text-subtext">暂无可预览内容</div>
            )}
          </div>
        </section>
      </div>

      {mobileListOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-end bg-black/30 lg:hidden"
          onClick={(e) => {
            if (e.target === e.currentTarget) setMobileListOpen(false);
          }}
          role="dialog"
          aria-modal="true"
          aria-label="章节列表"
        >
          <div className="h-[85vh] w-full overflow-hidden rounded-atelier border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <div className="text-sm text-ink">章节列表</div>
              <button
                className="inline-flex items-center gap-2 rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink hover:bg-surface"
                onClick={() => setMobileListOpen(false)}
                type="button"
              >
                <ChevronLeft size={16} />
                关闭
              </button>
            </div>
            {list}
          </div>
        </div>
      ) : null}

      <WizardNextBar projectId={projectId} currentStep="preview" progress={wizardProgress} loading={wizardLoading} />
    </div>
  );
}
