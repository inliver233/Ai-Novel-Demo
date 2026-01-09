import { useParams, useSearchParams } from "react-router-dom";

export function ChapterAnalysisPage() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const chapterId = searchParams.get("chapterId");

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="font-content text-2xl text-ink">章节标注回溯</div>
      <div className="mt-2 text-sm text-subtext">
        {projectId ? (
          <>
            project: <span className="font-mono">{projectId}</span>
          </>
        ) : (
          "缺少 projectId"
        )}
        {chapterId ? (
          <>
            {" "}
            / chapter: <span className="font-mono">{chapterId}</span>
          </>
        ) : null}
      </div>

      <div className="mt-6 rounded-atelier border border-border bg-surface p-4 text-sm text-subtext">
        此页面将在 Phase 2.5 完成：AnnotatedText 高亮 +
        侧栏筛选。请从写作页的“章节分析”弹窗完成分析后，点击“保存到记忆库” → “打开标注页”进入。
      </div>
    </div>
  );
}
