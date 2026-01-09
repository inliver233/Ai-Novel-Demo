import type { MemoryAnnotation } from "./types";

export type AnnotatedTextSegment =
  | { kind: "text"; text: string }
  | {
      kind: "annotated";
      text: string;
      start: number;
      end: number;
      groupAnnotations: MemoryAnnotation[];
      activeAnnotations: MemoryAnnotation[];
      primary: MemoryAnnotation;
    };

function pickPrimary(active: MemoryAnnotation[], group: MemoryAnnotation[]): MemoryAnnotation {
  const candidates = active.length > 0 ? active : group;
  let best = candidates[0];
  for (let i = 1; i < candidates.length; i++) {
    const it = candidates[i];
    if (it.importance > best.importance) best = it;
    else if (it.importance === best.importance && it.id < best.id) best = it;
  }
  return best;
}

type AnnotationSpan = {
  annotation: MemoryAnnotation;
  start: number;
  end: number;
};

function buildGroups(spans: AnnotationSpan[], adjacencyTolerance: number) {
  const sorted = [...spans].sort((a, b) => a.start - b.start || b.end - a.end);
  const groups: Array<{ start: number; end: number; spans: AnnotationSpan[] }> = [];

  let current: { start: number; end: number; spans: AnnotationSpan[] } | null = null;
  for (const span of sorted) {
    if (!current) {
      current = { start: span.start, end: span.end, spans: [span] };
      continue;
    }

    if (span.start <= current.end + adjacencyTolerance) {
      current.end = Math.max(current.end, span.end);
      current.spans.push(span);
      continue;
    }

    groups.push(current);
    current = { start: span.start, end: span.end, spans: [span] };
  }
  if (current) groups.push(current);
  return groups;
}

export function buildAnnotatedTextSegments(args: {
  content: string;
  annotations: MemoryAnnotation[];
  adjacencyTolerance?: number;
}): AnnotatedTextSegment[] {
  const content = args.content ?? "";
  const adjacencyTolerance = args.adjacencyTolerance ?? 5;

  const spans: AnnotationSpan[] = [];
  for (const ann of args.annotations ?? []) {
    const start = ann.position;
    const end = ann.position + ann.length;
    spans.push({ annotation: ann, start, end });
  }

  const groups = buildGroups(spans, adjacencyTolerance);
  const segments: AnnotatedTextSegment[] = [];

  let cursor = 0;
  for (const group of groups) {
    if (group.start > cursor) {
      segments.push({ kind: "text", text: content.slice(cursor, group.start) });
    }

    const groupAnnotations = group.spans.map((s) => s.annotation);
    const groupById = new Map<string, MemoryAnnotation>();
    for (const a of groupAnnotations) groupById.set(a.id, a);
    const dedupedGroup = Array.from(groupById.values()).sort(
      (a, b) => b.importance - a.importance || a.id.localeCompare(b.id),
    );

    const events: Array<{ pos: number; kind: "start" | "end"; ann: MemoryAnnotation }> = [];
    for (const span of group.spans) {
      events.push({ pos: span.start, kind: "start", ann: span.annotation });
      events.push({ pos: span.end, kind: "end", ann: span.annotation });
    }
    events.sort((a, b) => a.pos - b.pos || (a.kind === "end" ? -1 : 1));

    const activeById = new Map<string, MemoryAnnotation>();
    let pos = group.start;
    let idx = 0;

    while (idx < events.length) {
      const nextPos = events[idx].pos;
      if (nextPos > pos) {
        const active = Array.from(activeById.values());
        segments.push({
          kind: "annotated",
          text: content.slice(pos, nextPos),
          start: pos,
          end: nextPos,
          groupAnnotations: dedupedGroup,
          activeAnnotations: active,
          primary: pickPrimary(active, dedupedGroup),
        });
      }

      while (idx < events.length && events[idx].pos === nextPos) {
        const ev = events[idx];
        if (ev.kind === "end") activeById.delete(ev.ann.id);
        else activeById.set(ev.ann.id, ev.ann);
        idx++;
      }
      pos = nextPos;
    }

    if (pos < group.end) {
      const active = Array.from(activeById.values());
      segments.push({
        kind: "annotated",
        text: content.slice(pos, group.end),
        start: pos,
        end: group.end,
        groupAnnotations: dedupedGroup,
        activeAnnotations: active,
        primary: pickPrimary(active, dedupedGroup),
      });
    }

    cursor = group.end;
  }

  if (cursor < content.length) {
    segments.push({ kind: "text", text: content.slice(cursor) });
  }

  return segments;
}
