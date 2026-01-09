import { describe, expect, it } from "vitest";

import { buildAnnotatedTextSegments } from "./annotatedTextSegments";
import type { MemoryAnnotation } from "./types";

function ann(id: string, position: number, length: number, type = "hook", importance = 0.5): MemoryAnnotation {
  return {
    id,
    type,
    title: id,
    content: id,
    importance,
    position,
    length,
    tags: [],
    metadata: {},
  };
}

describe("buildAnnotatedTextSegments", () => {
  it("splits non-overlapping annotations into separate annotated segments", () => {
    const content = "abcdef";
    const segments = buildAnnotatedTextSegments({
      content,
      annotations: [ann("a1", 1, 2), ann("a2", 4, 1)],
      adjacencyTolerance: 0,
    });

    expect(segments.map((s) => s.text)).toEqual(["a", "bc", "d", "e", "f"]);
    expect(segments.filter((s) => s.kind === "annotated")).toHaveLength(2);
  });

  it("treats close ranges as a single group (adjacency tolerance)", () => {
    const content = "abcdef";
    const segments = buildAnnotatedTextSegments({
      content,
      annotations: [ann("a1", 1, 1), ann("a2", 3, 1)],
      adjacencyTolerance: 1,
    });

    expect(segments.map((s) => s.text)).toEqual(["a", "b", "c", "d", "ef"]);
    const annotated = segments.filter((s) => s.kind === "annotated");
    expect(annotated).toHaveLength(3);
    expect(annotated[1]?.activeAnnotations ?? []).toHaveLength(0);
    expect(annotated[1]?.groupAnnotations ?? []).toHaveLength(2);
  });

  it("keeps overlapping spans in one group and yields an overlap segment", () => {
    const content = "abcdefgh";
    const segments = buildAnnotatedTextSegments({
      content,
      annotations: [ann("a1", 1, 4, "hook", 0.4), ann("a2", 3, 3, "foreshadow", 0.9)],
      adjacencyTolerance: 0,
    });

    const annotated = segments.filter((s) => s.kind === "annotated");
    expect(annotated.map((s) => s.text)).toEqual(["bc", "de", "f"]);

    expect(annotated[0]?.activeAnnotations.map((a) => a.id)).toEqual(["a1"]);
    expect(annotated[1]?.activeAnnotations.map((a) => a.id).sort()).toEqual(["a1", "a2"]);
    expect(annotated[1]?.primary.id).toBe("a2");
  });
});
