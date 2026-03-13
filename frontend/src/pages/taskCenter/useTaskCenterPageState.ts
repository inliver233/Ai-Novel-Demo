import { type ComponentProps, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { useToast } from "../../components/ui/toast";
import { useProjectData } from "../../hooks/useProjectData";
import { useProjectTaskEvents } from "../../hooks/useProjectTaskEvents";
import { copyText } from "../../lib/copyText";
import { createRequestSeqGuard } from "../../lib/requestSeqGuard";
import { humanizeChangeSetStatus, humanizeTaskStatus } from "../../lib/humanize";
import { ApiError, apiJson } from "../../services/apiClient";
import {
  cancelBatchGenerationTask,
  getProjectTaskRuntime,
  pauseBatchGenerationTask,
  resumeBatchGenerationTask,
  retryFailedBatchGenerationTask,
  skipFailedBatchGenerationTask,
  type ProjectTaskRuntime,
} from "../../services/projectTaskRuntime";

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
  const projectTaskRefreshTimerRef = useRef<number | null>(null);
  const projectTaskDetailGuardRef = useRef(createRequestSeqGuard());
  const projectTaskRuntimeGuardRef = useRef(createRequestSeqGuard());
  const [selectedProjectTaskRuntime, setSelectedProjectTaskRuntime] = useState<ProjectTaskRuntime | null>(null);
  const [projectTaskRuntimeLoading, setProjectTaskRuntimeLoading] = useState(false);
  const [projectTaskBatchActionLoading, setProjectTaskBatchActionLoading] = useState(false);
  const [selected, setSelected] = useState<TaskCenterSelectedItem>(null);
  const [projectTaskDetailLoading, setProjectTaskDetailLoading] = useState(false);
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

  const loadProjectTasks = useCallback(
    async (id: string): Promise<PagedResult<ProjectTaskSummary>> => {
      const params = new URLSearchParams();
      if (projectTaskStatus !== "all") params.set("status", projectTaskStatus);
      params.set("limit", "50");
      const qs = params.toString();
      const response = await apiJson<PagedResult<ProjectTaskSummary>>(`/api/projects/${id}/tasks${qs ? `?${qs}` : ""}`);
      return response.data;
    },
    [projectTaskStatus],
  );

  const changeSetsQuery = useProjectData(projectId, loadChangeSets);
  const tasksQuery = useProjectData(projectId, loadTasks);
  const projectTasksQuery = useProjectData(projectId, loadProjectTasks);

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

  useEffect(() => {
    if (!projectId) return;
    void refreshProjectTasks();
  }, [projectId, projectTaskStatus, refreshProjectTasks]);

  const changeSets = useMemo(() => changeSetsQuery.data?.items ?? [], [changeSetsQuery.data?.items]);
  const tasks = useMemo(() => tasksQuery.data?.items ?? [], [tasksQuery.data?.items]);
  const projectTasks = useMemo(() => projectTasksQuery.data?.items ?? [], [projectTasksQuery.data?.items]);

  const changeSetSummary = useMemo(() => summarizeChangeSets(changeSets), [changeSets]);
  const taskSummary = useMemo(() => summarizeTasks(tasks), [tasks]);
  const projectTaskSummary = useMemo(() => summarizeTasks(projectTasks, { succeededAsDone: true }), [projectTasks]);

  const detailTitle = useMemo(() => getTaskCenterDetailTitle(selected), [selected]);
  const detailHeading = useMemo(() => getTaskCenterDetailHeading(selected), [selected]);

  const refreshAll = useCallback(() => {
    void refreshChangeSets();
    void refreshTasks();
    void refreshProjectTasks();
  }, [refreshChangeSets, refreshProjectTasks, refreshTasks]);

  const copyRequestId = useCallback(async (requestId: string) => {
    await copyText(requestId, { title: TASK_CENTER_COPY.requestIdCopyTitle });
  }, []);

  const copyRunId = useCallback(async (runId: string) => {
    await copyText(runId, { title: TASK_CENTER_COPY.runIdCopyTitle });
  }, []);

  const refreshSelectedProjectTask = useCallback(
    async (taskId: string, options?: { silent?: boolean; loading?: boolean }) => {
      const targetId = String(taskId || "").trim();
      if (!targetId) return;
      const seq = projectTaskDetailGuardRef.current.next();
      if (options?.loading) setProjectTaskDetailLoading(true);
      try {
        const response = await apiJson<ProjectTaskSummary>(`/api/tasks/${encodeURIComponent(targetId)}`);
        if (!projectTaskDetailGuardRef.current.isLatest(seq)) return;
        setSelected((prev) =>
          prev?.kind === "project_task" && prev.item.id === targetId
            ? { kind: "project_task", item: response.data }
            : prev,
        );
      } catch (error) {
        if (!projectTaskDetailGuardRef.current.isLatest(seq)) return;
        if (!options?.silent) {
          const err =
            error instanceof ApiError
              ? error
              : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
          toast.toastError(`${err.message} (${err.code})`, err.requestId);
        }
      } finally {
        if (options?.loading && projectTaskDetailGuardRef.current.isLatest(seq)) {
          setProjectTaskDetailLoading(false);
        }
      }
    },
    [toast],
  );

  const refreshSelectedProjectTaskRuntime = useCallback(
    async (taskId: string, options?: { silent?: boolean; loading?: boolean }) => {
      const targetId = String(taskId || "").trim();
      if (!targetId) return;
      const seq = projectTaskRuntimeGuardRef.current.next();
      if (options?.loading) setProjectTaskRuntimeLoading(true);
      try {
        const runtime = await getProjectTaskRuntime(targetId);
        if (!projectTaskRuntimeGuardRef.current.isLatest(seq)) return;
        setSelectedProjectTaskRuntime(runtime);
      } catch (error) {
        if (!projectTaskRuntimeGuardRef.current.isLatest(seq)) return;
        if (!options?.silent) {
          const err =
            error instanceof ApiError
              ? error
              : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
          toast.toastError(`${err.message} (${err.code})`, err.requestId);
        }
      } finally {
        if (options?.loading && projectTaskRuntimeGuardRef.current.isLatest(seq)) {
          setProjectTaskRuntimeLoading(false);
        }
      }
    },
    [toast],
  );

  const scheduleProjectTaskRefresh = useCallback(
    (taskId?: string | null) => {
      if (projectTaskRefreshTimerRef.current !== null) {
        window.clearTimeout(projectTaskRefreshTimerRef.current);
      }
      projectTaskRefreshTimerRef.current = window.setTimeout(() => {
        projectTaskRefreshTimerRef.current = null;
        void refreshProjectTasks();
        if (taskId && selected?.kind === "project_task" && selected.item.id === taskId) {
          void refreshSelectedProjectTask(taskId, { silent: true });
          void refreshSelectedProjectTaskRuntime(taskId, { silent: true });
        }
      }, 120);
    },
    [refreshProjectTasks, refreshSelectedProjectTask, refreshSelectedProjectTaskRuntime, selected],
  );

  useEffect(() => {
    const detailGuard = projectTaskDetailGuardRef.current;
    const runtimeGuard = projectTaskRuntimeGuardRef.current;
    return () => {
      detailGuard.invalidate();
      runtimeGuard.invalidate();
      if (projectTaskRefreshTimerRef.current !== null) {
        window.clearTimeout(projectTaskRefreshTimerRef.current);
      }
    };
  }, []);

  const projectTaskEvents = useProjectTaskEvents({
    projectId,
    enabled: Boolean(projectId),
    onSnapshot: (snapshot) => {
      if ((snapshot.active_tasks || []).length > 0) {
        scheduleProjectTaskRefresh(snapshot.active_tasks[0]?.id);
      }
    },
    onEvent: (event) => {
      scheduleProjectTaskRefresh(event.task_id);
    },
  });

  useEffect(() => {
    if (!projectId) return;
    if (projectTaskEvents.status === "open") return;
    const intervalId = window.setInterval(() => {
      void refreshProjectTasks();
      if (selected?.kind === "project_task") {
        void refreshSelectedProjectTask(selected.item.id, { silent: true });
        void refreshSelectedProjectTaskRuntime(selected.item.id, { silent: true });
      }
    }, 8000);
    return () => window.clearInterval(intervalId);
  }, [
    projectId,
    projectTaskEvents.status,
    refreshProjectTasks,
    refreshSelectedProjectTask,
    refreshSelectedProjectTaskRuntime,
    selected,
  ]);

  const projectTaskLiveStatusLabel = useMemo(
    () => getProjectTaskLiveStatusLabel(projectTaskEvents.status),
    [projectTaskEvents.status],
  );

  const copyDebugInfo = useCallback(async () => {
    if (!selected) return;
    if (selected.kind === "change_set") {
      const item = selected.item;
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

    if (selected.kind === "task") {
      const item = selected.item;
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

    const item = selected.item;
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
  }, [selected]);

  const copyRawJson = useCallback(async () => {
    if (!selected) return;
    await copyText(safeJsonStringify(selected.item), { title: TASK_CENTER_COPY.copyDebugInfoTitle });
  }, [selected]);

  const selectProjectTask = useCallback(
    async (task: ProjectTaskSummary) => {
      setSelected({ kind: "project_task", item: task });
      setSelectedProjectTaskRuntime(null);
      void refreshSelectedProjectTask(task.id, { loading: true });
      void refreshSelectedProjectTaskRuntime(task.id, { loading: true });
    },
    [refreshSelectedProjectTask, refreshSelectedProjectTaskRuntime],
  );

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
        await refreshProjectTasks();
        setSelected((prev) =>
          prev?.kind === "project_task" && prev.item.id === targetId
            ? { kind: "project_task", item: response.data }
            : prev,
        );
      } catch (error) {
        const err =
          error instanceof ApiError
            ? error
            : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [refreshProjectTasks, toast],
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
        await refreshProjectTasks();
        setSelected((prev) =>
          prev?.kind === "project_task" && prev.item.id === targetId
            ? { kind: "project_task", item: response.data }
            : prev,
        );
      } catch (error) {
        const err =
          error instanceof ApiError
            ? error
            : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [refreshProjectTasks, toast],
  );

  const runSelectedBatchAction = useCallback(
    async (action: "pause" | "resume" | "retry_failed" | "skip_failed" | "cancel") => {
      if (selected?.kind !== "project_task") return;
      const batchTaskId = String(selectedProjectTaskRuntime?.batch?.task.id || "").trim();
      if (!batchTaskId) return;
      const projectTaskId = selected.item.id;
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
        await refreshProjectTasks();
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
      selected,
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
    setSelectedProjectTaskRuntime(null);
    void refreshSelectedProjectTask(targetId, { loading: true });
    void refreshSelectedProjectTaskRuntime(targetId, { loading: true });
  }, [autoOpenedProjectTask, projectId, refreshSelectedProjectTask, refreshSelectedProjectTaskRuntime, searchParams]);

  useEffect(() => {
    if (selected?.kind === "project_task") return;
    projectTaskRuntimeGuardRef.current.invalidate();
    setSelectedProjectTaskRuntime(null);
    setProjectTaskRuntimeLoading(false);
    setProjectTaskBatchActionLoading(false);
  }, [selected]);

  const selectedProjectTaskChangeSetId = useMemo(() => {
    if (selected?.kind !== "project_task") return null;
    return extractChangeSetIdFromProjectTaskResult(selected.item.result);
  }, [selected]);

  const selectedProjectTaskChangeSetStatus = useMemo(() => {
    if (selected?.kind !== "project_task") return null;
    return extractChangeSetStatusFromProjectTaskResult(selected.item.result);
  }, [selected]);

  const selectedProjectTaskRunId = useMemo(() => {
    if (selected?.kind !== "project_task") return null;
    return (
      extractRunIdFromProjectTaskError(selected.item.error) || extractRunIdFromProjectTaskResult(selected.item.result)
    );
  }, [selected]);

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
      selected,
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
        if (selected?.kind !== "project_task") return;
        void selectProjectTask(selected.item);
      },
      onRetryProjectTask: (taskId) => void retryProjectTask(taskId),
      onCancelProjectTask: (taskId) => void cancelProjectTask(taskId),
      onRefreshProjectTaskRuntime: () => {
        if (selected?.kind !== "project_task") return;
        void refreshSelectedProjectTaskRuntime(selected.item.id, { loading: true });
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
