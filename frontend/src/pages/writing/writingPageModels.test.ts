import { describe, expect, it } from "vitest";

import {
  buildBatchTaskCenterHref,
  buildProjectTaskCenterHref,
  buildWritingTaskCenterHref,
  pickFirstProjectTaskId,
} from "./writingPageModels";

describe("writingPageModels", () => {
  it("picks the first non-empty task id", () => {
    expect(pickFirstProjectTaskId(null)).toBeNull();
    expect(pickFirstProjectTaskId({ a: null, b: "  ", c: "task-1" })).toBe("task-1");
  });

  it("builds stable task center links", () => {
    expect(buildWritingTaskCenterHref("p1")).toBe("/projects/p1/tasks");
    expect(buildWritingTaskCenterHref("p1", "c1")).toBe("/projects/p1/tasks?chapterId=c1");
    expect(buildProjectTaskCenterHref("p1", "task-1")).toBe("/projects/p1/tasks?project_task_id=task-1");
    expect(buildBatchTaskCenterHref("p1", "task-1")).toBe("/projects/p1/tasks?project_task_id=task-1");
    expect(buildBatchTaskCenterHref("p1", null)).toBeNull();
  });
});
