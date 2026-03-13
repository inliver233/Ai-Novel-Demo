import { describe, expect, it } from "vitest";

import {
  getProjectTaskLiveStatusLabel,
  getTaskCenterDetailHeading,
  getTaskCenterDetailTitle,
  summarizeChangeSets,
  summarizeTasks,
  type TaskCenterSelectedItem,
} from "./taskCenterModels";

describe("taskCenterModels", () => {
  it("summarizes change sets by status", () => {
    const summary = summarizeChangeSets([
      { id: "1", status: "proposed" },
      { id: "2", status: "applied" },
      { id: "3", status: "rolled_back" },
      { id: "4", status: "failed" },
      { id: "5", status: "other" },
    ]);

    expect(summary).toEqual({
      all: 5,
      proposed: 1,
      applied: 1,
      rolled_back: 1,
      failed: 1,
      other: 1,
    });
  });

  it("summarizes tasks and treats succeeded as done when requested", () => {
    const items = [
      { id: "1", project_id: "p", change_set_id: "c", kind: "a", status: "queued" },
      { id: "2", project_id: "p", change_set_id: "c", kind: "a", status: "running" },
      { id: "3", project_id: "p", change_set_id: "c", kind: "a", status: "done" },
      { id: "4", project_id: "p", change_set_id: "c", kind: "a", status: "succeeded" },
      { id: "5", project_id: "p", change_set_id: "c", kind: "a", status: "failed" },
    ];

    expect(summarizeTasks(items)).toMatchObject({ queued: 1, running: 1, done: 1, failed: 1, other: 1 });
    expect(summarizeTasks(items, { succeededAsDone: true })).toMatchObject({ done: 2, other: 0 });
  });

  it("derives detail copy from selected item kind", () => {
    const selectedTask = {
      kind: "task",
      item: { id: "1", project_id: "p", change_set_id: "c", kind: "a", status: "done" },
    } as TaskCenterSelectedItem;
    const selectedProjectTask = {
      kind: "project_task",
      item: { id: "2", project_id: "p", kind: "b", status: "failed" },
    } as TaskCenterSelectedItem;

    expect(getTaskCenterDetailTitle(selectedTask)).toBe("Task 详情");
    expect(getTaskCenterDetailHeading(selectedTask)).toBe("任务详情");
    expect(getTaskCenterDetailTitle(selectedProjectTask)).toBe("ProjectTask 详情");
    expect(getTaskCenterDetailHeading(selectedProjectTask)).toBe("项目任务详情");
  });

  it("maps project task stream state into stable UI labels", () => {
    expect(getProjectTaskLiveStatusLabel("open")).toBe("connected");
    expect(getProjectTaskLiveStatusLabel("connecting")).toBe("reconnecting");
    expect(getProjectTaskLiveStatusLabel("error")).toBe("fallback polling");
    expect(getProjectTaskLiveStatusLabel("idle")).toBe("idle");
  });
});
