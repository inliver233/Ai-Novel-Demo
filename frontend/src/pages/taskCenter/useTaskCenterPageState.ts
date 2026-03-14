import { type ComponentProps, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { useToast } from "../../components/ui/toast";
import { useProjectData } from "../../hooks/useProjectData";
import {
  useProjectTaskDetailResource,
  useProjectTaskListResource,
  useProjectTaskLiveSync,
  useProjectTaskRuntimeResource,
} from "../../hooks/useProjectTaskRuntimeResource";
import { copyText } from "../../lib/copyText";
import { humanizeChangeSetStatus, humanizeTaskStatus } from "../../lib/humanize";
import { ApiError, apiJson } from "../../services/apiClient";
import {
  cancelBatchGenerationTask,
  pauseBatchGenerationTask,
  resumeBatchGenerationTask,
  retryFailedBatchGenerationTask,
  skipFailedBatchGenerationTask,
} from "../../services/projectTaskRuntime";
import { projectTaskStore } from "../../services/projectTaskStore";

import {
  extractChangeSetIdFromProjectTaskResult,
  extractChangeSetStatusFromProjectTaskResult,
  extractRunIdFromProjectTaskError,
  extractRunIdFromProjectTaskResult,
  safeJsonStringify,
} from "./helpers";
import {
  TaskCenterChangeSetsSection,
  TaskCenterDetailDrawer,
  TaskCenterHealthBanner,
  TaskCenterHelpSection,
  TaskCenterProjectTasksSection,
  TaskCenterTasksSection,
} from "./TaskCenterPageSections";
import { TASK_CENTER_COPY } from "./taskCenterCopy";
import {
  getProjectTaskLiveStatusLabel,
  getTaskCenterDetailHeading,
  getTaskCenterDetailTitle,
  summarizeChangeSets,
  summarizeTasks,
  type ChangeSetApplyResult,
  type HealthData,
  type MemoryChangeSetSummary,
  type MemoryTaskSummary,
  type PagedResult,
  type ProjectTaskSummary,
  type TaskCenterSelectedItem,
} from "./taskCenterModels";

type TaskCenterPageState = {
  projectId?: string;
  onRefreshAll: () => void;
  healthBannerProps: ComponentProps<typeof TaskCenterHealthBanner>;
  helpSectionProps: ComponentProps<typeof TaskCenterHelpSection>;
  changeSetsSectionProps: ComponentProps<typeof TaskCenterChangeSetsSection>;
  tasksSectionProps: ComponentProps<typeof TaskCenterTasksSection>;
  projectTasksSectionProps: ComponentProps<typeof TaskCenterProjectTasksSection>;
  detailDrawerProps: ComponentProps<typeof TaskCenterDetailDrawer>;
};

export function useTaskCenterPageState(): TaskCenterPageState {
  const { projectId } = useParams();
  const toast = useToast();
  const [searchParams] = useSearchParams();

  const [health, setHealth] = useState<{ data: HealthData; requestId: string } | null>(null);
  const [changeSetStatus, setChangeSetStatus] = useState<string>("all");
  const [taskStatus, setTaskStatus] = useState<string>("all");
  const [projectTaskStatus, setProjectTaskStatus] = useState<string>("all");
  const [autoOpenedProjectTask, setAutoOpenedProjectTask] = useState(false);
  const [projectTaskBatchActionLoading, setProjectTaskBatchActionLoading] = useState(false);
  const [selected, setSelected] = useState<TaskCenterSelectedItem>(null);
  const [changeSetActionLoading, setChangeSetActionLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiJson<HealthData>("/api/health")
      .then((response) => {
        if (cancelled) return;
        setHealth({ data: response.data, requestId: response.request_id });
      })
      .catch(() => {
        if (cancelled) return;
        setHealth(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadChangeSets = useCallback(
    async (id: string): Promise<PagedResult<MemoryChangeSetSummary>> => {
      const params = new URLSearchParams();
      if (changeSetStatus !== "all") params.set("status", changeSetStatus);
      params.set("limit", "50");
      const qs = params.toString();
      const response = await apiJson<PagedResult<MemoryChangeSetSummary>>(
        `/api/projects/${id}/memory_change_sets${qs ? `?${qs}` : ""}`,
      );
      return response.data;
    },
    [changeSetStatus],
  );

  const loadTasks = useCallback(
    async (id: string): Promise<PagedResult<MemoryTaskSummary>> => {
      const params = new URLSearchParams();
      if (taskStatus !== "all") params.set("status", taskStatus);
      params.set("limit", "50");
      const qs = params.toString();
      const response = await apiJson<PagedResult<MemoryTaskSummary>>(
        `/api/projects/${id}/memory_tasks${qs ? `?${qs}` : ""}`,
      );
      return response.data;
    },
    [taskStatus],
  );

  const changeSetsQuery = useProjectData(projectId, loadChangeSets);
  const tasksQuery = useProjectData(projectId, loadTasks);
  const projectTasksQuery = useProjectTaskListResource({
    projectId,
    status: projectTaskStatus,
    enabled: Boolean(projectId),
  });

  const refreshChangeSets = changeSetsQuery.refresh;
  const refreshTasks = tasksQuery.refresh;
  const refreshProjectTasks = projectTasksQuery.refresh;

  useEffect(() => {
    if (!projectId) return;
    void refreshChangeSets();
  }, [changeSetStatus, projectId, refreshChangeSets]);

  useEffect(() => {
    if (!projectId) return;
    void refreshTasks();
  }, [projectId, refreshTasks, taskStatus]);

  const changeSets = useMemo(() => changeSetsQuery.data?.items ?? [], [changeSetsQuery.data?.items]);
  const tasks = useMemo(() => tasksQuery.data?.items ?? [], [tasksQuery.data?.items]);
  const projectTasks = useMemo(() => projectTasksQuery.data ?? [], [projectTasksQuery.data]);

  const selectedProjectTaskId = selected?.kind === "project_task" ? selected.item.id : null;
  const selectedProjectTaskProjectId =
    selected?.kind === "project_task"
      ? selected.item.project_id || projectTaskStore.tryGetProjectIdForTask(selected.item.id) || projectId || ""
      : "";
  const projectTaskDetailResource = useProjectTaskDetailResource({
    taskId: selectedProjectTaskId,
    enabled: selected?.kind === "project_task",
  });
  const projectTaskRuntimeResource = useProjectTaskRuntimeResource({
    taskId: selectedProjectTaskId,
    enabled: selected?.kind === "project_task",
  });
  const selectedProjectTask = useMemo(() => {
    if (selected?.kind !== "project_task") return null;
    return projectTaskDetailResource.data ?? selected.item;
  }, [projectTaskDetailResource.data, selected]);
  const detailSelected = useMemo<TaskCenterSelectedItem>(() => {
    if (selected?.kind !== "project_task" || !selectedProjectTask) return selected;
    return { kind: "project_task", item: selectedProjectTask };
  }, [selected, selectedProjectTask]);
  const selectedProjectTaskRuntime = projectTaskRuntimeResource.data;
  const projectTaskDetailLoading = detailSelected?.kind === "project_task" ? projectTaskDetailResource.loading : false;
  const projectTaskRuntimeLoading =
    detailSelected?.kind === "project_task" ? projectTaskRuntimeResource.loading : false;

  const changeSetSummary = useMemo(() => summarizeChangeSets(changeSets), [changeSets]);
  const taskSummary = useMemo(() => summarizeTasks(tasks), [tasks]);
  const projectTaskSummary = useMemo(() => summarizeTasks(projectTasks, { succeededAsDone: true }), [projectTasks]);

  const detailTitle = useMemo(() => getTaskCenterDetailTitle(detailSelected), [detailSelected]);
  const detailHeading = useMemo(() => getTaskCenterDetailHeading(detailSelected), [detailSelected]);

  const refreshAll = useCallback(() => {
    void refreshChangeSets();
    void refreshTasks();
    void refreshProjectTasks({ force: true });
    if (selectedProjectTaskId) {
      void projectTaskDetailResource.refresh({ taskId: selectedProjectTaskId, force: true, silent: true });
      void projectTaskRuntimeResource.refresh({ taskId: selectedProjectTaskId, force: true, silent: true });
    }
  }, [
    projectTaskDetailResource,
    projectTaskRuntimeResource,
    refreshChangeSets,
    refreshProjectTasks,
    refreshTasks,
    selectedProjectTaskId,
  ]);

  const copyRequestId = useCallback(async (requestId: string) => {
    await copyText(requestId, { title: TASK_CENTER_COPY.requestIdCopyTitle });
  }, []);

  const copyRunId = useCallback(async (runId: string) => {
    await copyText(runId, { title: TASK_CENTER_COPY.runIdCopyTitle });
  }, []);

  const refreshSelectedProjectTask = useCallback(
    async (taskId: string, options?: { silent?: boolean }) => {
      await projectTaskDetailResource.refresh({ taskId, force: true, silent: options?.silent });
    },
    [projectTaskDetailResource],
  );

  const refreshSelectedProjectTaskRuntime = useCallback(
    async (taskId: string, options?: { silent?: boolean }) => {
      await projectTaskRuntimeResource.refresh({ taskId, force: true, silent: options?.silent });
    },
    [projectTaskRuntimeResource],
  );

  const projectTaskEvents = useProjectTaskLiveSync({
    projectId,
    enabled: Boolean(projectId),
    trackedTaskId: selectedProjectTaskId,
    pollWhen: Boolean(projectId),
    pickSnapshotTaskId: (snapshot) => snapshot.active_tasks[0]?.id ?? null,
    shouldRefreshOnEvent: () => true,
    onRefresh: (taskId) => {
      void refreshProjectTasks({ force: true, silent: true });
      const targetId = String(taskId || "").trim();
      if (selectedProjectTaskId && (!targetId || targetId === selectedProjectTaskId)) {
        void refreshSelectedProjectTask(selectedProjectTaskId, { silent: true });
        void refreshSelectedProjectTaskRuntime(selectedProjectTaskId, { silent: true });
      }
    },
  });

  const projectTaskLiveStatusLabel = useMemo(
    () => getProjectTaskLiveStatusLabel(projectTaskEvents.status),
    [projectTaskEvents.status],
  );

  const copyDebugInfo = useCallback(async () => {
    if (!detailSelected) return;
    if (detailSelected.kind === "change_set") {
      const item = detailSelected.item;
      await copyText(
        [
          "[TaskCenter][ChangeSet]",
          `id=${item.id}`,
          `status=${String(item.status || "-")} (${humanizeChangeSetStatus(String(item.status || ""))})`,
          `chapter_id=${item.chapter_id || "-"}`,
          `request_id=${item.request_id || "-"}`,
          `idempotency_key=${item.idempotency_key || "-"}`,
          `created_at=${item.created_at || "-"}`,
          `updated_at=${item.updated_at || "-"}`,
        ].join("\n"),
        { title: TASK_CENTER_COPY.copyDebugInfoTitle },
      );
      return;
    }

    if (detailSelected.kind === "task") {
      const item = detailSelected.item;
      await copyText(
        [
          "[TaskCenter][Task]",
          `id=${item.id}`,
          `kind=${item.kind}`,
          `status=${String(item.status || "-")} (${humanizeTaskStatus(String(item.status || ""))})`,
          `change_set_id=${item.change_set_id}`,
          `request_id=${item.request_id || "-"}`,
          `error_type=${item.error_type || "-"}`,
          `error_message=${item.error_message || "-"}`,
          `error=${safeJsonStringify(item.error ?? null)}`,
        ].join("\n"),
        { title: TASK_CENTER_COPY.copyDebugInfoTitle },
      );
      return;
    }

    const item = detailSelected.item;
    await copyText(
      [
        "[TaskCenter][ProjectTask]",
        `id=${item.id}`,
        `kind=${item.kind}`,
        `status=${String(item.status || "-")} (${humanizeTaskStatus(String(item.status || ""))})`,
        `idempotency_key=${item.idempotency_key || "-"}`,
        `error_type=${item.error_type || "-"}`,
        `error_message=${item.error_message || "-"}`,
        `error=${safeJsonStringify(item.error ?? null)}`,
      ].join("\n"),
      { title: TASK_CENTER_COPY.copyDebugInfoTitle },
    );
  }, [detailSelected]);

  const copyRawJson = useCallback(async () => {
    if (!detailSelected) return;
    await copyText(safeJsonStringify(detailSelected.item), { title: TASK_CENTER_COPY.copyDebugInfoTitle });
  }, [detailSelected]);

  const selectProjectTask = useCallback(async (task: ProjectTaskSummary) => {
    projectTaskStore.setProjectTaskDetail(task);
    projectTaskStore.invalidateProjectTaskDetail(task.id);
    setSelected({ kind: "project_task", item: task });
  }, []);

  const retryProjectTask = useCallback(
    async (taskId: string) => {
      const targetId = String(taskId || "").trim();
      if (!targetId) return;
      try {
        const response = await apiJson<ProjectTaskSummary>(`/api/tasks/${encodeURIComponent(targetId)}/retry`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        toast.toastSuccess(TASK_CENTER_COPY.projectTasksRetryToast, response.request_id);
        projectTaskStore.setProjectTaskDetail(response.data);
        projectTaskStore.invalidateProjectTaskLists(response.data.project_id);
        await refreshProjectTasks({ force: true, silent: true });
        if (selectedProjectTaskId === targetId) {
          await refreshSelectedProjectTask(targetId, { silent: true });
          await refreshSelectedProjectTaskRuntime(targetId, { silent: true });
        }
      } catch (error) {
        const err =
          error instanceof ApiError
            ? error
            : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [refreshProjectTasks, refreshSelectedProjectTask, refreshSelectedProjectTaskRuntime, selectedProjectTaskId, toast],
  );

  const cancelProjectTask = useCallback(
    async (taskId: string) => {
      const targetId = String(taskId || "").trim();
      if (!targetId) return;
      if (!window.confirm(TASK_CENTER_COPY.cancelQueuedProjectTaskConfirm)) return;
      try {
        const response = await apiJson<ProjectTaskSummary>(`/api/tasks/${encodeURIComponent(targetId)}/cancel`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        toast.toastSuccess(TASK_CENTER_COPY.projectTasksCancelToast, response.request_id);
        projectTaskStore.setProjectTaskDetail(response.data);
        projectTaskStore.invalidateProjectTaskLists(response.data.project_id);
        await refreshProjectTasks({ force: true, silent: true });
        if (selectedProjectTaskId === targetId) {
          await refreshSelectedProjectTask(targetId, { silent: true });
          await refreshSelectedProjectTaskRuntime(targetId, { silent: true });
        }
      } catch (error) {
        const err =
          error instanceof ApiError
            ? error
            : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [refreshProjectTasks, refreshSelectedProjectTask, refreshSelectedProjectTaskRuntime, selectedProjectTaskId, toast],
  );

  const runSelectedBatchAction = useCallback(
    async (action: "pause" | "resume" | "retry_failed" | "skip_failed" | "cancel") => {
      if (detailSelected?.kind !== "project_task") return;
      const batchTaskId = String(selectedProjectTaskRuntime?.batch?.task.id || "").trim();
      if (!batchTaskId) return;
      const projectTaskId = detailSelected.item.id;
      setProjectTaskBatchActionLoading(true);
      try {
        if (action === "pause") {
          await pauseBatchGenerationTask(batchTaskId);
          toast.toastSuccess(TASK_CENTER_COPY.runtimeBatchPausedToast);
        } else if (action === "resume") {
          await resumeBatchGenerationTask(batchTaskId);
          toast.toastSuccess(TASK_CENTER_COPY.runtimeBatchResumedToast);
        } else if (action === "retry_failed") {
          await retryFailedBatchGenerationTask(batchTaskId);
          toast.toastSuccess(TASK_CENTER_COPY.runtimeBatchRetryFailedToast);
        } else if (action === "skip_failed") {
          await skipFailedBatchGenerationTask(batchTaskId);
          toast.toastSuccess(TASK_CENTER_COPY.runtimeBatchSkipFailedToast);
        } else {
          if (!window.confirm(TASK_CENTER_COPY.cancelBatchConfirm)) return;
          await cancelBatchGenerationTask(batchTaskId);
          toast.toastSuccess(TASK_CENTER_COPY.runtimeBatchCanceledToast);
        }
        if (selectedProjectTaskProjectId) {
          projectTaskStore.invalidateProjectTaskLists(selectedProjectTaskProjectId);
        }
        projectTaskStore.invalidateProjectTaskDetail(projectTaskId);
        projectTaskStore.invalidateProjectTaskRuntime(projectTaskId);
        await refreshProjectTasks({ force: true, silent: true });
        await Promise.all([
          refreshSelectedProjectTask(projectTaskId, { silent: true }),
          refreshSelectedProjectTaskRuntime(projectTaskId, { silent: true }),
        ]);
      } catch (error) {
        const err =
          error instanceof ApiError
            ? error
            : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setProjectTaskBatchActionLoading(false);
      }
    },
    [
      refreshProjectTasks,
      refreshSelectedProjectTask,
      refreshSelectedProjectTaskRuntime,
      detailSelected,
      selectedProjectTaskProjectId,
      selectedProjectTaskRuntime,
      toast,
    ],
  );

  const applyChangeSet = useCallback(
    async (changeSetId: string) => {
      const targetId = String(changeSetId || "").trim();
      if (!targetId) return;
      setChangeSetActionLoading(true);
      try {
        const response = await apiJson<ChangeSetApplyResult>(
          `/api/memory_change_sets/${encodeURIComponent(targetId)}/apply`,
          {
            method: "POST",
            body: JSON.stringify({}),
          },
        );
        toast.toastSuccess(TASK_CENTER_COPY.detailApplyChangeSetToast, response.request_id);
        await refreshChangeSets();
      } catch (error) {
        const err =
          error instanceof ApiError
            ? error
            : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setChangeSetActionLoading(false);
      }
    },
    [refreshChangeSets, toast],
  );

  const rollbackChangeSet = useCallback(
    async (changeSetId: string) => {
      const targetId = String(changeSetId || "").trim();
      if (!targetId) return;
      setChangeSetActionLoading(true);
      try {
        const response = await apiJson<ChangeSetApplyResult>(
          `/api/memory_change_sets/${encodeURIComponent(targetId)}/rollback`,
          {
            method: "POST",
            body: JSON.stringify({}),
          },
        );
        toast.toastSuccess(TASK_CENTER_COPY.detailRollbackChangeSetToast, response.request_id);
        await refreshChangeSets();
      } catch (error) {
        const err =
          error instanceof ApiError
            ? error
            : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setChangeSetActionLoading(false);
      }
    },
    [refreshChangeSets, toast],
  );

  useEffect(() => {
    if (!projectId) return;
    const targetId = String(searchParams.get("project_task_id") || "").trim();
    if (!targetId || autoOpenedProjectTask) return;
    setAutoOpenedProjectTask(true);
    projectTaskStore.touchProjectTaskDetail(targetId, projectId);
    void projectTaskStore.loadProjectTaskDetail(targetId).catch(() => undefined);
    void projectTaskStore.loadProjectTaskRuntime(targetId).catch(() => undefined);
  }, [autoOpenedProjectTask, projectId, searchParams]);

  useEffect(() => {
    if (detailSelected?.kind === "project_task") return;
    setProjectTaskBatchActionLoading(false);
  }, [detailSelected]);

  const selectedProjectTaskChangeSetId = useMemo(() => {
    if (detailSelected?.kind !== "project_task") return null;
    return (
      extractChangeSetIdFromProjectTaskResult(detailSelected.item.result) ||
      (selected?.kind === "project_task" ? extractChangeSetIdFromProjectTaskResult(selected.item.result) : null)
    );
  }, [detailSelected, selected]);

  const selectedProjectTaskChangeSetStatus = useMemo(() => {
    if (detailSelected?.kind !== "project_task") return null;
    return (
      extractChangeSetStatusFromProjectTaskResult(detailSelected.item.result) ||
      (selected?.kind === "project_task" ? extractChangeSetStatusFromProjectTaskResult(selected.item.result) : null)
    );
  }, [detailSelected, selected]);

  const selectedProjectTaskRunId = useMemo(() => {
    if (detailSelected?.kind !== "project_task") return null;
    return (
      extractRunIdFromProjectTaskError(detailSelected.item.error) ||
      extractRunIdFromProjectTaskResult(detailSelected.item.result) ||
      (selected?.kind === "project_task"
        ? extractRunIdFromProjectTaskError(selected.item.error) ||
          extractRunIdFromProjectTaskResult(selected.item.result)
        : null)
    );
  }, [detailSelected, selected]);

  const liveChangeSetStatus = useMemo(() => {
    const id = selectedProjectTaskChangeSetId;
    if (!id) return selectedProjectTaskChangeSetStatus;
    const live = changeSets.find((item) => item.id === id);
    return (live?.status ? String(live.status) : null) ?? selectedProjectTaskChangeSetStatus;
  }, [changeSets, selectedProjectTaskChangeSetId, selectedProjectTaskChangeSetStatus]);

  return {
    projectId,
    onRefreshAll: refreshAll,
    healthBannerProps: {
      health,
      onCopyRequestId: (requestId) => void copyRequestId(requestId),
    },
    helpSectionProps: {
      projectId,
    },
    changeSetsSectionProps: {
      loading: changeSetsQuery.loading,
      items: changeSets,
      summary: changeSetSummary,
      status: changeSetStatus,
      onStatusChange: setChangeSetStatus,
      onSelect: (item) => setSelected({ kind: "change_set", item }),
      onCopyRequestId: (requestId) => void copyRequestId(requestId),
    },
    tasksSectionProps: {
      loading: tasksQuery.loading,
      items: tasks,
      summary: taskSummary,
      status: taskStatus,
      onStatusChange: setTaskStatus,
      onToggleFailedOnly: () => setTaskStatus((prev) => (prev === "failed" ? "all" : "failed")),
      onSelect: (item) => setSelected({ kind: "task", item }),
      onCopyRequestId: (requestId) => void copyRequestId(requestId),
    },
    projectTasksSectionProps: {
      loading: projectTasksQuery.loading,
      items: projectTasks,
      summary: projectTaskSummary,
      status: projectTaskStatus,
      liveStatusLabel: projectTaskLiveStatusLabel,
      onStatusChange: setProjectTaskStatus,
      onToggleFailedOnly: () => setProjectTaskStatus((prev) => (prev === "failed" ? "all" : "failed")),
      onSelect: (item) => void selectProjectTask(item),
      onRetry: (taskId) => void retryProjectTask(taskId),
      onCancel: (taskId) => void cancelProjectTask(taskId),
    },
    detailDrawerProps: {
      selected: detailSelected,
      detailTitle,
      detailHeading,
      projectTaskDetailLoading,
      selectedProjectTaskRuntime,
      projectTaskRuntimeLoading,
      projectTaskBatchActionLoading,
      selectedProjectTaskChangeSetId,
      liveChangeSetStatus,
      selectedProjectTaskRunId,
      changeSetActionLoading,
      onClose: () => setSelected(null),
      onCopyDebugInfo: () => void copyDebugInfo(),
      onCopyRawJson: () => void copyRawJson(),
      onCopyRequestId: (requestId) => void copyRequestId(requestId),
      onCopyRunId: (runId) => void copyRunId(runId),
      onRefreshProjectTaskDetail: () => {
        if (detailSelected?.kind !== "project_task") return;
        void refreshSelectedProjectTask(detailSelected.item.id);
      },
      onRetryProjectTask: (taskId) => void retryProjectTask(taskId),
      onCancelProjectTask: (taskId) => void cancelProjectTask(taskId),
      onRefreshProjectTaskRuntime: () => {
        if (detailSelected?.kind !== "project_task") return;
        void refreshSelectedProjectTaskRuntime(detailSelected.item.id);
      },
      onPauseBatch: () => void runSelectedBatchAction("pause"),
      onResumeBatch: () => void runSelectedBatchAction("resume"),
      onRetryFailedBatch: () => void runSelectedBatchAction("retry_failed"),
      onSkipFailedBatch: () => void runSelectedBatchAction("skip_failed"),
      onCancelBatch: () => void runSelectedBatchAction("cancel"),
      onApplyChangeSet: (changeSetId) => void applyChangeSet(changeSetId),
      onRollbackChangeSet: (changeSetId) => void rollbackChangeSet(changeSetId),
    },
  };
}
