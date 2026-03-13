import { DebugPageShell } from "../components/atelier/DebugPageShell";
import { UI_COPY } from "../lib/uiCopy";

import {
  TaskCenterChangeSetsSection,
  TaskCenterDetailDrawer,
  TaskCenterHealthBanner,
  TaskCenterHelpSection,
  TaskCenterProjectTasksSection,
  TaskCenterTasksSection,
} from "./taskCenter/TaskCenterPageSections";
import { TASK_CENTER_COPY } from "./taskCenter/taskCenterCopy";
import { useTaskCenterPageState } from "./taskCenter/useTaskCenterPageState";

export function TaskCenterPage() {
  const state = useTaskCenterPageState();

  if (!state.projectId) return <div className="text-subtext">{TASK_CENTER_COPY.missingProjectId}</div>;

  return (
    <DebugPageShell
      title={UI_COPY.taskCenter.title}
      description={UI_COPY.taskCenter.subtitle}
      actions={
        <button
          className="btn btn-secondary"
          onClick={state.onRefreshAll}
          aria-label="刷新 (taskcenter_refresh)"
          type="button"
        >
          {TASK_CENTER_COPY.refresh}
        </button>
      }
    >
      <TaskCenterHealthBanner {...state.healthBannerProps} />
      <TaskCenterHelpSection {...state.helpSectionProps} />

      <div className="grid gap-4 lg:grid-cols-2">
        <TaskCenterChangeSetsSection {...state.changeSetsSectionProps} />
        <TaskCenterTasksSection {...state.tasksSectionProps} />
        <TaskCenterProjectTasksSection {...state.projectTasksSectionProps} />
      </div>

      <TaskCenterDetailDrawer {...state.detailDrawerProps} />
    </DebugPageShell>
  );
}
