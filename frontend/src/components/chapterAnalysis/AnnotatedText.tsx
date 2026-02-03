import clsx from "clsx";
import { useEffect, useMemo, useRef } from "react";

import { buildAnnotatedTextSegments } from "./annotatedTextSegments";
import type { MemoryAnnotation } from "./types";
import { labelForAnnotationType } from "./types";

function buildTooltipText(annotations: MemoryAnnotation[]): string {
  const pieces: string[] = [];
  const sorted = [...annotations].sort((a, b) => b.importance - a.importance || a.id.localeCompare(b.id));
  for (const a of sorted) {
    const title = (a.title ?? "").trim();
    const head = `${labelForAnnotationType(a.type)} · ${title || "（无标题）"} · ${(a.importance * 10).toFixed(1)}/10`;
    const snippet = (a.content ?? "").trim().slice(0, 120);
    pieces.push(snippet ? `${head}\n${snippet}` : head);
  }
  return pieces.join("\n\n");
}

function colorClassForType(type: string): { border: string; activeBg: string; hoverBg: string } {
  switch (type) {
    case "hook":
      return { border: "border-accent/70", activeBg: "bg-accent/10", hoverBg: "hover:bg-accent/5" };
    case "foreshadow":
      return { border: "border-info/70", activeBg: "bg-info/10", hoverBg: "hover:bg-info/5" };
    case "plot_point":
      return { border: "border-success/70", activeBg: "bg-success/10", hoverBg: "hover:bg-success/5" };
    case "character_state":
      return { border: "border-warning/70", activeBg: "bg-warning/10", hoverBg: "hover:bg-warning/5" };
    case "chapter_summary":
      return { border: "border-border", activeBg: "bg-canvas/60", hoverBg: "hover:bg-canvas/40" };
    default:
      return { border: "border-border", activeBg: "bg-canvas/60", hoverBg: "hover:bg-canvas/40" };
  }
}

export function AnnotatedText(props: {
  content: string;
  annotations: MemoryAnnotation[];
  activeAnnotationId?: string | null;
  scrollToAnnotationId?: string | null;
  onAnnotationClick?: (annotation: MemoryAnnotation) => void;
  className?: string;
}) {
  const refsByIdRef = useRef<Map<string, { pos: number; el: HTMLButtonElement }>>(new Map());
  const segments = useMemo(
    () =>
      buildAnnotatedTextSegments({
        content: props.content,
        annotations: props.annotations,
        adjacencyTolerance: 5,
      }),
    [props.annotations, props.content],
  );

  useEffect(() => {
    if (!props.scrollToAnnotationId) return;
    const target = refsByIdRef.current.get(props.scrollToAnnotationId)?.el;
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [props.scrollToAnnotationId, segments]);

  return (
    <div
      className={clsx(
        "min-w-0 max-w-full whitespace-pre-wrap break-words font-content text-sm leading-relaxed text-ink",
        props.className,
      )}
    >
      {segments.map((segment, idx) => {
        if (segment.kind === "text") {
          return <span key={`t-${idx}`}>{segment.text}</span>;
        }

        const activeId = props.activeAnnotationId ?? null;
        const isActive = activeId ? segment.activeAnnotations.some((a) => a.id === activeId) : false;
        const colors = colorClassForType(segment.primary.type);
        const title = buildTooltipText(segment.groupAnnotations);

        return (
          <button
            type="button"
            key={`a-${idx}-${segment.primary.id}-${segment.start}`}
            ref={(el) => {
              if (!el) return;
              for (const ann of segment.activeAnnotations) {
                const existing = refsByIdRef.current.get(ann.id);
                if (!existing || !existing.el.isConnected || segment.start < existing.pos) {
                  refsByIdRef.current.set(ann.id, { pos: segment.start, el });
                }
              }
            }}
            className={clsx(
              "ui-focus-ring ui-transition-fast cursor-pointer break-words rounded-sm border-b-2 px-0.5 py-0.5",
              colors.border,
              colors.hoverBg,
              isActive ? colors.activeBg : "bg-transparent",
            )}
            title={title}
            onClick={() => props.onAnnotationClick?.(segment.primary)}
            data-annotation-id={segment.primary.id}
          >
            {segment.text}
          </button>
        );
      })}
    </div>
  );
}
