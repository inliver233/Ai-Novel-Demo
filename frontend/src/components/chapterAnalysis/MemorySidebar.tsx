import clsx from "clsx";
import { useMemo, useState } from "react";

import type { MemoryAnnotation } from "./types";
import { labelForAnnotationType, sortKeyForAnnotationType } from "./types";

function normalizeTitle(annotation: MemoryAnnotation): string {
  const title = (annotation.title ?? "").trim();
  if (title) return title;
  const content = (annotation.content ?? "").trim();
  if (content) return content.slice(0, 60);
  return "（无标题）";
}

export function MemorySidebar(props: {
  annotations: MemoryAnnotation[];
  validIds: Set<string>;
  activeAnnotationId?: string | null;
  onSelect: (annotation: MemoryAnnotation) => void;
}) {
  const allTypes = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of props.annotations) {
      counts.set(a.type, (counts.get(a.type) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([type, count]) => ({ type, count }))
      .sort(
        (a, b) => sortKeyForAnnotationType(a.type) - sortKeyForAnnotationType(b.type) || a.type.localeCompare(b.type),
      );
  }, [props.annotations]);

  const [enabledTypes, setEnabledTypes] = useState<Set<string>>(() => new Set(allTypes.map((t) => t.type)));

  const filtered = useMemo(() => {
    const out = props.annotations.filter((a) => enabledTypes.has(a.type));
    out.sort(
      (a, b) => sortKeyForAnnotationType(a.type) - sortKeyForAnnotationType(b.type) || b.importance - a.importance,
    );
    return out;
  }, [enabledTypes, props.annotations]);

  const groups = useMemo(() => {
    const map = new Map<string, MemoryAnnotation[]>();
    for (const a of filtered) {
      const list = map.get(a.type) ?? [];
      list.push(a);
      map.set(a.type, list);
    }
    return Array.from(map.entries()).sort(
      (a, b) => sortKeyForAnnotationType(a[0]) - sortKeyForAnnotationType(b[0]) || a[0].localeCompare(b[0]),
    );
  }, [filtered]);

  const invalidCount = props.annotations.length - props.validIds.size;

  return (
    <aside className="min-w-0 grid gap-2">
      <div className="rounded-atelier border border-border bg-surface p-2">
        <div className="text-sm text-ink">记忆侧栏</div>
        <div className="mt-1 text-xs text-subtext">
          共 {props.annotations.length} 条{invalidCount > 0 ? `（${invalidCount} 条未定位）` : ""}
        </div>

        <div className="mt-2 flex flex-wrap gap-2">
          {allTypes.map((t) => {
            const enabled = enabledTypes.has(t.type);
            return (
              <button
                key={t.type}
                className={clsx("btn btn-ghost px-2 py-1 text-xs", enabled ? "bg-canvas text-ink" : "text-subtext")}
                type="button"
                onClick={() => {
                  setEnabledTypes((prev) => {
                    const next = new Set(prev);
                    if (next.has(t.type)) next.delete(t.type);
                    else next.add(t.type);
                    if (next.size === 0) return new Set([t.type]);
                    return next;
                  });
                }}
                aria-pressed={enabled}
                title={enabled ? "点击取消过滤" : "点击启用过滤"}
              >
                {labelForAnnotationType(t.type)}
                <span className="ml-1 text-subtext">· {t.count}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="rounded-atelier border border-border bg-surface p-2">
        {groups.length === 0 ? (
          <div className="p-3 text-sm text-subtext">暂无记忆。请先在写作页分析并“保存到记忆库”。</div>
        ) : (
          <div className="grid gap-3">
            {groups.map(([type, list]) => (
              <section key={type} className="grid gap-2">
                <div className="px-1 text-xs text-subtext">
                  {labelForAnnotationType(type)} · {list.length}
                </div>
                <div className="grid gap-2">
                  {list.map((a) => {
                    const active = props.activeAnnotationId === a.id;
                    const valid = props.validIds.has(a.id);
                    return (
                      <button
                        key={a.id}
                        className={clsx(
                          "ui-transition-fast w-full rounded-atelier border px-3 py-2 text-left",
                          active ? "border-accent bg-canvas" : "border-border bg-canvas hover:bg-surface",
                          !valid && "opacity-70",
                        )}
                        type="button"
                        onClick={() => props.onSelect(a)}
                        title={valid ? "点击定位到正文" : "未定位：无法在正文中高亮"}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-sm text-ink">{normalizeTitle(a)}</div>
                            <div className="mt-1 line-clamp-2 text-xs text-subtext">
                              {(a.content ?? "").trim().slice(0, 140)}
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="text-xs text-subtext">{(a.importance * 10).toFixed(1)}</div>
                            {!valid ? <div className="mt-1 text-xs text-accent">未定位</div> : null}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
