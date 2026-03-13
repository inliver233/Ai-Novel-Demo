import { Link } from "react-router-dom";

import { Badge } from "../../components/ui/Badge";
import { Drawer } from "../../components/ui/Drawer";
import { humanizeTaskStatus } from "../../lib/humanize";
import { UI_COPY } from "../../lib/uiCopy";
import type {
  ProjectTask,
  WorldBookEntry,
  WorldBookExportAllV1,
  WorldBookImportAllReport,
  WorldBookImportMode,
  WorldBookPreviewTriggerResult,
  WorldBookPriority,
} from "../../services/worldbookApi";

import { WORLDBOOK_COPY } from "./worldbookCopy";
import {
  highlightText,
  taskStatusTone,
  WORLD_BOOK_ENTRY_RENDER_THRESHOLD,
  type WorldBookEntryForm,
  type WorldBookFilterMeta,
} from "./worldbookModels";
import type { WorldBookSortMode } from "./useWorldBookFilters";

type PreviewErrorState = {
  message: string;
  code: string;
  requestId?: string;
} | null;

type PreviewPanelProps = {
  variant: "page" | "drawer";
  requestId: string | null;
  queryText: string;
  onQueryTextChange: (value: string) => void;
  includeConstant: boolean;
  onIncludeConstantChange: (value: boolean) => void;
  enableRecursion: boolean;
  onEnableRecursionChange: (value: boolean) => void;
  charLimit: number;
  onCharLimitChange: (value: number) => void;
  loading: boolean;
  error: PreviewErrorState;
  result: WorldBookPreviewTriggerResult | null;
  disabled: boolean;
  disabledHint?: string;
  onRun: () => void;
  triggeredListOpenByDefault: boolean;
};

export type WorldBookPageActionsBarProps = {
  filteredCount: number;
  totalCount: number;
  projectId?: string;
  exporting: boolean;
  onRefresh: () => void;
  onExport: () => void;
  onOpenImport: () => void;
  onOpenNew: () => void;
};

export function WorldBookPageActionsBar(props: WorldBookPageActionsBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="text-sm text-subtext">
        {UI_COPY.worldbook.entriesCountPrefix}
        {props.filteredCount}
        {props.filteredCount === props.totalCount ? "" : ` / ${props.totalCount}`}
        {UI_COPY.worldbook.entriesCountSuffix}
      </div>
      <div className="flex gap-2">
        <button className="btn btn-secondary" onClick={props.onRefresh} type="button">
          {UI_COPY.worldbook.refresh}
        </button>
        <button
          className="btn btn-secondary"
          disabled={!props.projectId || props.exporting}
          onClick={props.onExport}
          type="button"
        >
          {props.exporting ? WORLDBOOK_COPY.exporting : WORLDBOOK_COPY.exportJson}
        </button>
        <button className="btn btn-secondary" disabled={!props.projectId} onClick={props.onOpenImport} type="button">
          {WORLDBOOK_COPY.importJson}
        </button>
        <button className="btn btn-primary" onClick={props.onOpenNew} type="button">
          {UI_COPY.worldbook.create}
        </button>
      </div>
    </div>
  );
}

export type WorldBookAutoUpdateSectionProps = {
  projectId?: string;
  loading: boolean;
  actionLoading: boolean;
  task: ProjectTask | null | undefined;
  onRefresh: () => void;
  onRetry: () => void;
  onTrigger: () => void;
};

export function WorldBookAutoUpdateSection(props: WorldBookAutoUpdateSectionProps) {
  return (
    <div className="panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-ink">{WORLDBOOK_COPY.autoUpdateTitle}</div>
          <div className="mt-1 text-xs text-subtext">{WORLDBOOK_COPY.autoUpdateHint}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="btn btn-secondary"
            disabled={!props.projectId || props.actionLoading}
            onClick={props.onRefresh}
            type="button"
          >
            {WORLDBOOK_COPY.autoUpdateRefresh}
          </button>
          <button
            className="btn btn-secondary"
            disabled={!props.projectId || props.actionLoading || props.task?.status !== "failed"}
            onClick={props.onRetry}
            type="button"
          >
            {WORLDBOOK_COPY.autoUpdateRetry}
          </button>
          <button
            className="btn btn-primary"
            disabled={!props.projectId || props.actionLoading}
            onClick={props.onTrigger}
            type="button"
          >
            {props.actionLoading ? WORLDBOOK_COPY.autoUpdateProcessing : WORLDBOOK_COPY.autoUpdateTrigger}
          </button>
          {props.projectId ? (
            <Link className="btn btn-secondary" to={`/projects/${props.projectId}/tasks`}>
              {WORLDBOOK_COPY.autoUpdateTaskCenter}
            </Link>
          ) : (
            <button className="btn btn-secondary" disabled type="button">
              {WORLDBOOK_COPY.autoUpdateTaskCenter}
            </button>
          )}
        </div>
      </div>

      <div className="mt-3">
        {props.loading ? <div className="text-xs text-subtext">{UI_COPY.common.loading}</div> : null}
        {!props.loading && !props.task ? (
          <div className="text-xs text-subtext">{WORLDBOOK_COPY.autoUpdateEmpty}</div>
        ) : null}
        {props.task ? (
          <div className="grid gap-1 text-xs text-subtext">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={taskStatusTone(props.task.status)}>{humanizeTaskStatus(props.task.status)}</Badge>
              <span className="font-mono text-subtext">{props.task.kind}</span>
              <span className="font-mono text-subtext">({props.task.id})</span>
            </div>

            <div className="flex flex-wrap gap-2">
              <span>{WORLDBOOK_COPY.autoUpdateRequestId}</span>
              <span className="font-mono text-ink">
                {typeof (props.task.params as Record<string, unknown> | null)?.request_id === "string"
                  ? ((props.task.params as Record<string, unknown>).request_id as string)
                  : "-"}
              </span>
            </div>

            <div className="flex flex-wrap gap-2">
              <span>{WORLDBOOK_COPY.autoUpdateChapterId}</span>
              <span className="font-mono text-ink">
                {typeof (props.task.params as Record<string, unknown> | null)?.chapter_id === "string"
                  ? ((props.task.params as Record<string, unknown>).chapter_id as string)
                  : "-"}
              </span>
            </div>

            <div className="flex flex-wrap gap-2">
              <span>{WORLDBOOK_COPY.autoUpdateRunId}</span>
              <span className="font-mono text-ink">
                {typeof (props.task.result as Record<string, unknown> | null)?.run_id === "string"
                  ? ((props.task.result as Record<string, unknown>).run_id as string)
                  : "-"}
              </span>
            </div>

            {typeof (props.task.result as Record<string, unknown> | null)?.applied === "object" &&
            (props.task.result as Record<string, unknown>).applied ? (
              <div className="flex flex-wrap gap-2">
                <span>{WORLDBOOK_COPY.autoUpdateApplied}</span>
                <span className="font-mono text-ink">
                  {JSON.stringify((props.task.result as Record<string, unknown>).applied)}
                </span>
              </div>
            ) : null}

            {props.task.status === "failed" ? (
              <div className="text-xs text-danger">
                {props.task.error_type ? `${props.task.error_type}: ` : ""}
                {props.task.error_message || WORLDBOOK_COPY.autoUpdateFailedFallback}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export type WorldBookEntriesSectionProps = {
  loading: boolean;
  searchText: string;
  onSearchTextChange: (value: string) => void;
  sortMode: WorldBookSortMode;
  onSortModeChange: (value: WorldBookSortMode) => void;
  bulkMode: boolean;
  onBulkModeChange: (value: boolean) => void;
  bulkLoading: boolean;
  bulkSelectedCount: number;
  bulkHiddenSelectedCount: number;
  onBulkSelectAll: () => void;
  onBulkClearSelection: () => void;
  onBulkEnable: () => void;
  onBulkDisable: () => void;
  onBulkDuplicateEdit: () => void;
  onBulkDelete: () => void;
  bulkPriority: WorldBookPriority;
  onBulkPriorityChange: (value: WorldBookPriority) => void;
  onApplyBulkPriority: () => void;
  bulkCharLimit: number;
  onBulkCharLimitChange: (value: number) => void;
  onApplyBulkCharLimit: () => void;
  filteredEntries: WorldBookEntry[];
  visibleEntries: WorldBookEntry[];
  filterTokens: string[];
  filterMetaById: Map<string, WorldBookFilterMeta>;
  bulkSelectAllActive: boolean;
  bulkSelectedExplicitSet: Set<string>;
  bulkExcludedSet: Set<string>;
  onToggleEntrySelection: (entryId: string) => void;
  onOpenEntry: (entry: WorldBookEntry) => void;
  drawerOpen: boolean;
  paginateEntries: boolean;
  entryPageStart: number;
  entryPageEnd: number;
  entryPageIndex: number;
  totalEntryPages: number;
  onPrevPage: () => void;
  onNextPage: () => void;
};

export function WorldBookEntriesSection(props: WorldBookEntriesSectionProps) {
  return (
    <div className="panel p-4">
      <div className="text-sm text-ink">{UI_COPY.worldbook.entriesTitle}</div>
      <div className="mt-1 text-xs text-subtext">{UI_COPY.worldbook.entriesHint}</div>

      {props.loading ? <div className="mt-3 text-sm text-subtext">{UI_COPY.common.loading}</div> : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 sm:col-span-2">
          <span className="text-xs text-subtext">{WORLDBOOK_COPY.searchLabel}</span>
          <input
            id="worldbook_search"
            className="input"
            value={props.searchText}
            onChange={(event) => props.onSearchTextChange(event.target.value)}
            aria-label="worldbook_search"
            placeholder={WORLDBOOK_COPY.searchPlaceholder}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">{WORLDBOOK_COPY.sortLabel}</span>
          <select
            id="worldbook_sort"
            className="select"
            value={props.sortMode}
            onChange={(event) => props.onSortModeChange(event.target.value as WorldBookSortMode)}
            aria-label="worldbook_sort"
          >
            {WORLDBOOK_COPY.sortOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center justify-between gap-2 text-sm text-ink">
          <span>{UI_COPY.worldbook.bulkMode}</span>
          <input
            id="worldbook_bulk_mode"
            className="checkbox"
            checked={props.bulkMode}
            disabled={props.bulkLoading}
            onChange={(event) => props.onBulkModeChange(event.target.checked)}
            aria-label="worldbook_bulk_mode"
            type="checkbox"
          />
        </label>
      </div>

      {props.bulkMode ? (
        <div className="mt-4 rounded-atelier border border-border bg-canvas p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs text-subtext">
              {UI_COPY.worldbook.bulkSelectedPrefix}
              {props.bulkSelectedCount}
              {UI_COPY.worldbook.bulkSelectedSuffix}
              {props.bulkHiddenSelectedCount > 0 ? (
                <span className="ml-2">
                  {WORLDBOOK_COPY.hiddenSelectionPrefix}
                  {props.bulkHiddenSelectedCount}
                  {WORLDBOOK_COPY.hiddenSelectionSuffix}
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-secondary"
                disabled={props.bulkLoading || props.loading}
                onClick={props.onBulkSelectAll}
                aria-label="worldbook_bulk_select_all"
                type="button"
              >
                {UI_COPY.worldbook.bulkSelectAll}
              </button>
              <button
                className="btn btn-secondary"
                disabled={props.bulkLoading || props.loading}
                onClick={props.onBulkClearSelection}
                aria-label="worldbook_bulk_clear_selection"
                type="button"
              >
                {UI_COPY.worldbook.bulkClearSelection}
              </button>
            </div>
          </div>
          <div className="mt-2 text-[11px] text-subtext">{UI_COPY.worldbook.bulkModeHint}</div>

          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="btn btn-secondary"
              disabled={props.bulkLoading || props.loading || props.drawerOpen}
              onClick={props.onBulkEnable}
              aria-label="worldbook_bulk_enable"
              type="button"
            >
              {UI_COPY.worldbook.bulkEnable}
            </button>
            <button
              className="btn btn-secondary"
              disabled={props.bulkLoading || props.loading || props.drawerOpen}
              onClick={props.onBulkDisable}
              aria-label="worldbook_bulk_disable"
              type="button"
            >
              {UI_COPY.worldbook.bulkDisable}
            </button>
            <button
              className="btn btn-secondary"
              disabled={props.bulkLoading || props.loading || props.drawerOpen || props.bulkSelectedCount !== 1}
              onClick={props.onBulkDuplicateEdit}
              aria-label="worldbook_bulk_duplicate_edit"
              type="button"
            >
              {UI_COPY.worldbook.bulkDuplicateEdit}
            </button>
            <button
              className="btn btn-danger"
              disabled={props.bulkLoading || props.loading || props.drawerOpen}
              onClick={props.onBulkDelete}
              aria-label="worldbook_bulk_delete"
              type="button"
            >
              {UI_COPY.worldbook.bulkDelete}
            </button>
          </div>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="flex items-end gap-2">
              <label className="grid flex-1 gap-1">
                <span className="text-xs text-subtext">{UI_COPY.worldbook.bulkPriority}</span>
                <select
                  id="worldbook_bulk_priority"
                  className="select"
                  value={props.bulkPriority}
                  onChange={(event) => props.onBulkPriorityChange(event.target.value as WorldBookPriority)}
                  disabled={props.bulkLoading || props.loading}
                  aria-label="worldbook_bulk_priority"
                >
                  {WORLDBOOK_COPY.priorityOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="btn btn-secondary"
                disabled={props.bulkLoading || props.loading || props.drawerOpen}
                onClick={props.onApplyBulkPriority}
                aria-label="worldbook_bulk_apply_priority"
                type="button"
              >
                {UI_COPY.worldbook.bulkApply}
              </button>
            </div>

            <div className="flex items-end gap-2">
              <label className="grid flex-1 gap-1">
                <span className="text-xs text-subtext">{UI_COPY.worldbook.bulkCharLimit}</span>
                <input
                  id="worldbook_bulk_char_limit"
                  className="input"
                  min={0}
                  type="number"
                  value={props.bulkCharLimit}
                  onChange={(event) => props.onBulkCharLimitChange(event.currentTarget.valueAsNumber)}
                  disabled={props.bulkLoading || props.loading}
                  aria-label="worldbook_bulk_char_limit"
                />
              </label>
              <button
                className="btn btn-secondary"
                disabled={props.bulkLoading || props.loading || props.drawerOpen}
                onClick={props.onApplyBulkCharLimit}
                aria-label="worldbook_bulk_apply_char_limit"
                type="button"
              >
                {UI_COPY.worldbook.bulkApply}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="mt-4 grid gap-3">
        {props.filteredEntries.length === 0 ? (
          <div className="text-sm text-subtext">{UI_COPY.worldbook.empty}</div>
        ) : (
          props.visibleEntries.map((entry) => {
            const selected = props.bulkSelectAllActive
              ? !props.bulkExcludedSet.has(entry.id)
              : props.bulkSelectedExplicitSet.has(entry.id);
            const meta = props.filterMetaById.get(entry.id) ?? { pinyinHit: false };
            const keywordSnippet = (entry.keywords ?? []).slice(0, 6).join("、") || UI_COPY.worldbook.keywordsNone;
            return (
              <button
                key={entry.id}
                className={
                  props.bulkMode && selected
                    ? "panel-interactive ui-focus-ring border-accent/60 bg-surface-hover p-4 text-left"
                    : "panel-interactive ui-focus-ring p-4 text-left"
                }
                disabled={props.bulkMode && props.bulkLoading}
                onClick={() => (props.bulkMode ? props.onToggleEntrySelection(entry.id) : props.onOpenEntry(entry))}
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    {props.bulkMode ? (
                      <div className="mt-1 shrink-0" aria-hidden="true">
                        <div
                          className={
                            selected
                              ? "flex h-5 w-5 items-center justify-center rounded-atelier border border-accent bg-accent text-[rgb(var(--color-on-accent))] text-xs"
                              : "h-5 w-5 rounded-atelier border border-border bg-canvas"
                          }
                        >
                          {selected ? "✓" : null}
                        </div>
                      </div>
                    ) : null}
                    <div className="min-w-0">
                      <div className="truncate font-content text-lg text-ink">
                        {highlightText(entry.title, props.filterTokens)}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-subtext">
                        <span>{entry.enabled ? UI_COPY.worldbook.tagEnabled : UI_COPY.worldbook.tagDisabled}</span>
                        <span>{entry.constant ? UI_COPY.worldbook.tagBlue : UI_COPY.worldbook.tagGreen}</span>
                        <span>{UI_COPY.worldbook.tagPriorityPrefix + entry.priority}</span>
                        <span>{UI_COPY.worldbook.tagCharLimitPrefix + entry.char_limit}</span>
                        {props.filterTokens.length && meta.pinyinHit ? (
                          <span className="rounded border border-border bg-surface px-1 py-0.5 text-[10px] text-subtext">
                            {WORLDBOOK_COPY.pinyinTag}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>
                  <div className="shrink-0 text-[11px] text-subtext">{entry.updated_at}</div>
                </div>
                {entry.constant ? null : (
                  <div className="mt-2 line-clamp-2 text-xs text-subtext">
                    {UI_COPY.worldbook.keywordsPrefix}
                    {highlightText(keywordSnippet, props.filterTokens)}
                  </div>
                )}
              </button>
            );
          })
        )}
      </div>

      {props.paginateEntries ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
          <div>
            {WORLDBOOK_COPY.paginationInfoPrefix}
            {props.entryPageStart + 1}-{props.entryPageEnd}/{props.filteredEntries.length}
            {WORLDBOOK_COPY.paginationInfoMiddle}
            {WORLD_BOOK_ENTRY_RENDER_THRESHOLD}
            {WORLDBOOK_COPY.paginationInfoSuffix}
            <span className="ml-2">
              {WORLDBOOK_COPY.paginationPagePrefix}
              {props.entryPageIndex + 1}
              {WORLDBOOK_COPY.paginationPageSeparator}
              {props.totalEntryPages}
              {WORLDBOOK_COPY.paginationPageSuffix}
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-secondary"
              disabled={props.entryPageIndex === 0}
              onClick={props.onPrevPage}
              aria-label="worldbook_page_prev"
              type="button"
            >
              {WORLDBOOK_COPY.paginationPrev}
            </button>
            <button
              className="btn btn-secondary"
              disabled={props.entryPageIndex >= props.totalEntryPages - 1}
              onClick={props.onNextPage}
              aria-label="worldbook_load_more"
              type="button"
            >
              {WORLDBOOK_COPY.paginationNext}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function WorldBookPreviewPanel(props: PreviewPanelProps) {
  const inputPrefix = props.variant === "page" ? "worldbook" : "worldbook_entry";
  const cardSurfaceClassName = props.variant === "page" ? "bg-surface" : "bg-canvas";
  const errorSurfaceClassName = props.variant === "page" ? "bg-surface" : "bg-canvas";

  return (
    <>
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm text-ink">{UI_COPY.worldbook.previewTitle}</div>
          <div className="mt-1 text-xs text-subtext">
            {UI_COPY.worldbook.previewHint}
            {props.requestId ? <span className="ml-2">request_id: {props.requestId}</span> : null}
          </div>
        </div>
        <div className="grid justify-items-end gap-1">
          <button
            className="btn btn-secondary"
            disabled={props.loading || props.disabled}
            title={props.disabled ? props.disabledHint : undefined}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              props.onRun();
            }}
            type="button"
          >
            {UI_COPY.worldbook.previewRun}
          </button>
          {props.disabled && props.disabledHint ? (
            <Badge className="max-w-[320px] whitespace-normal" tone="warning">
              {props.disabledHint}
            </Badge>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid gap-3">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">{UI_COPY.worldbook.previewQueryLabel}</span>
          <textarea
            id={`${inputPrefix}_preview_query_text`}
            className="textarea atelier-content"
            name="query_text"
            rows={props.variant === "page" ? 4 : 3}
            value={props.queryText}
            onChange={(event) => props.onQueryTextChange(event.target.value)}
          />
        </label>

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex items-center justify-between gap-2 text-sm text-ink">
            <span>{UI_COPY.worldbook.previewIncludeConstant}</span>
            <input
              id={`${inputPrefix}_preview_include_constant`}
              className="checkbox"
              checked={props.includeConstant}
              name="include_constant"
              onChange={(event) => props.onIncludeConstantChange(event.target.checked)}
              type="checkbox"
            />
          </label>
          <label className="flex items-center justify-between gap-2 text-sm text-ink">
            <span>{UI_COPY.worldbook.previewEnableRecursion}</span>
            <input
              id={`${inputPrefix}_preview_enable_recursion`}
              className="checkbox"
              checked={props.enableRecursion}
              name="enable_recursion"
              onChange={(event) => props.onEnableRecursionChange(event.target.checked)}
              type="checkbox"
            />
          </label>
          <label className="grid gap-1 sm:col-span-2">
            <span className="text-xs text-subtext">{UI_COPY.worldbook.previewCharLimit}</span>
            <input
              id={`${inputPrefix}_preview_char_limit`}
              className="input"
              min={0}
              name="char_limit"
              type="number"
              value={props.charLimit}
              onChange={(event) => props.onCharLimitChange(event.currentTarget.valueAsNumber)}
            />
          </label>
        </div>

        {props.loading ? <div className="text-sm text-subtext">{UI_COPY.common.loading}</div> : null}
        {props.error ? (
          <div className={`rounded-atelier border border-border ${errorSurfaceClassName} p-3 text-sm text-subtext`}>
            <div className="text-ink">{UI_COPY.worldbook.previewFailed}</div>
            <div className="mt-1 text-xs text-subtext">
              {props.error.message} ({props.error.code})
              {props.error.requestId ? <span className="ml-2">request_id: {props.error.requestId}</span> : null}
            </div>
          </div>
        ) : null}

        {props.result ? (
          <div className="grid gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
              <span>
                {UI_COPY.worldbook.previewTriggeredPrefix}
                {props.result.triggered.length}
                {UI_COPY.worldbook.previewTriggeredSuffix}
              </span>
              {props.result.truncated ? (
                <Badge className="shrink-0" tone="warning">
                  {UI_COPY.worldbook.previewTruncated}
                </Badge>
              ) : null}
            </div>
            <details open={props.triggeredListOpenByDefault}>
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                {UI_COPY.worldbook.previewTriggeredList}
              </summary>
              <div className="mt-2 grid gap-2">
                {props.result.triggered.length === 0 ? (
                  <div className="text-sm text-subtext">{UI_COPY.worldbook.previewNoTriggered}</div>
                ) : (
                  props.result.triggered.map((entry) => (
                    <div
                      key={entry.id}
                      className={`rounded-atelier border border-border ${cardSurfaceClassName} p-2 text-xs`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-ink">{entry.title}</div>
                          <div className="mt-1 text-subtext">
                            {entry.reason} | priority:{entry.priority}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </details>
            <details open>
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                {UI_COPY.worldbook.previewText}
              </summary>
              <pre
                className={`mt-2 max-h-64 overflow-auto rounded-atelier border border-border ${cardSurfaceClassName} p-3 text-xs text-ink`}
              >
                {props.result.text_md || UI_COPY.worldbook.previewTextEmpty}
              </pre>
            </details>
          </div>
        ) : null}
      </div>
    </>
  );
}

export type WorldBookImportDrawerProps = {
  open: boolean;
  loading: boolean;
  mode: WorldBookImportMode;
  fileName: string;
  importJson: WorldBookExportAllV1 | null;
  report: WorldBookImportAllReport | null;
  onClose: () => void;
  onLoadFile: (file: File | null) => void;
  onModeChange: (mode: WorldBookImportMode) => void;
  onDryRun: () => void;
  onApply: () => void;
};

export function WorldBookImportDrawer(props: WorldBookImportDrawerProps) {
  return (
    <Drawer
      open={props.open}
      onClose={props.onClose}
      ariaLabel={WORLDBOOK_COPY.importDrawerTitle}
      panelClassName="h-full w-full max-w-xl border-l border-border bg-canvas p-6 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-content text-2xl text-ink">{WORLDBOOK_COPY.importDrawerTitle}</div>
          <div className="mt-1 text-xs text-subtext">{WORLDBOOK_COPY.importDrawerHint}</div>
        </div>
        <button className="btn btn-secondary" disabled={props.loading} onClick={props.onClose} type="button">
          {UI_COPY.worldbook.close}
        </button>
      </div>

      <div className="mt-5 grid gap-4">
        <div className="surface p-4">
          <div className="text-sm text-ink">{WORLDBOOK_COPY.importFileTitle}</div>
          <div className="mt-3 grid gap-3">
            <label className="grid gap-1">
              <span className="text-xs text-subtext">{WORLDBOOK_COPY.importFileLabel}</span>
              <input
                id="worldbook_import_file"
                aria-label={WORLDBOOK_COPY.importFileLabel}
                className="input"
                accept="application/json,.json"
                onChange={(event) => props.onLoadFile(event.target.files?.[0] ?? null)}
                type="file"
              />
            </label>

            <label className="grid gap-1">
              <span className="text-xs text-subtext">{WORLDBOOK_COPY.importModeLabel}</span>
              <select
                id="worldbook_import_mode"
                aria-label={WORLDBOOK_COPY.importModeLabel}
                className="select"
                disabled={props.loading}
                value={props.mode}
                onChange={(event) => props.onModeChange(event.target.value as WorldBookImportMode)}
              >
                <option value="merge">{WORLDBOOK_COPY.importModeMerge}</option>
                <option value="overwrite">{WORLDBOOK_COPY.importModeOverwrite}</option>
              </select>
            </label>

            <div className="text-[11px] text-subtext">{WORLDBOOK_COPY.importModeHint}</div>

            {props.fileName ? (
              <div className="text-xs text-subtext">
                {WORLDBOOK_COPY.importSelectedPrefix}
                {props.fileName}
              </div>
            ) : null}
            {props.importJson ? (
              <div className="text-xs text-subtext">
                {WORLDBOOK_COPY.importSchemaVersionLabel}{" "}
                <span className="text-ink">{props.importJson.schema_version}</span> |{" "}
                {WORLDBOOK_COPY.importEntriesLabel}{" "}
                <span className="text-ink">{props.importJson.entries?.length ?? 0}</span>
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <button
                className="btn btn-secondary"
                disabled={!props.importJson || props.loading}
                onClick={props.onDryRun}
                type="button"
              >
                {props.loading ? WORLDBOOK_COPY.importProcessing : WORLDBOOK_COPY.importDryRunButton}
              </button>
              <button
                className="btn btn-primary"
                disabled={!props.importJson || props.loading}
                onClick={props.onApply}
                type="button"
              >
                {props.loading ? WORLDBOOK_COPY.importApplying : WORLDBOOK_COPY.importApplyButton}
              </button>
            </div>
          </div>
        </div>

        {props.report ? (
          <div className="surface p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-ink">{WORLDBOOK_COPY.importReportTitle}</div>
                <div className="mt-1 text-xs text-subtext">
                  dry_run: {String(props.report.dry_run)} | mode: {props.report.mode}
                </div>
                <div className="mt-1 text-[11px] text-subtext">{WORLDBOOK_COPY.importReportExplain}</div>
              </div>
            </div>

            <div className="mt-3 grid gap-1 text-xs text-subtext">
              <div>
                created: <span className="text-ink">{props.report.created}</span> | updated:{" "}
                <span className="text-ink">{props.report.updated}</span> | deleted:{" "}
                <span className="text-ink">{props.report.deleted}</span> | skipped:{" "}
                <span className="text-ink">{props.report.skipped}</span>
              </div>
              <div className="text-[11px] text-subtext">{WORLDBOOK_COPY.importReportCountsExplain}</div>
              <div>
                conflicts: <span className="text-ink">{props.report.conflicts?.length ?? 0}</span> | actions:{" "}
                <span className="text-ink">{props.report.actions?.length ?? 0}</span>
              </div>
            </div>

            <details className="mt-3" open>
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                {WORLDBOOK_COPY.importReportConflicts}({props.report.conflicts?.length ?? 0})
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                {JSON.stringify(props.report.conflicts ?? [], null, 2)}
              </pre>
            </details>

            <details className="mt-3">
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                {WORLDBOOK_COPY.importReportActions}({props.report.actions?.length ?? 0})
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                {JSON.stringify(props.report.actions ?? [], null, 2)}
              </pre>
            </details>
          </div>
        ) : null}
      </div>
    </Drawer>
  );
}

export type WorldBookEditorDrawerProps = {
  open: boolean;
  editing: WorldBookEntry | null;
  form: WorldBookEntryForm;
  saving: boolean;
  bulkLoading: boolean;
  dirty: boolean;
  onUpdateForm: (patch: Partial<WorldBookEntryForm>) => void;
  onDelete: () => void;
  onDuplicate: () => void;
  onClose: () => void;
  onSave: () => void;
  previewPanelProps: Omit<PreviewPanelProps, "variant">;
};

export function WorldBookEditorDrawer(props: WorldBookEditorDrawerProps) {
  return (
    <Drawer
      open={props.open}
      onClose={props.onClose}
      ariaLabel={UI_COPY.worldbook.drawerTitle}
      panelClassName="h-full w-full max-w-2xl border-l border-border bg-canvas p-6 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-content text-2xl text-ink">{UI_COPY.worldbook.drawerTitle}</div>
          <div className="mt-1 text-xs text-subtext">
            {props.editing ? props.editing.id : UI_COPY.worldbook.newEntryHint}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {props.editing ? (
            <button className="btn btn-secondary" disabled={props.saving} onClick={props.onDelete} type="button">
              {UI_COPY.worldbook.delete}
            </button>
          ) : null}
          {props.editing ? (
            <button
              className="btn btn-secondary"
              disabled={props.saving || props.bulkLoading}
              onClick={props.onDuplicate}
              type="button"
            >
              {UI_COPY.worldbook.bulkDuplicateEdit}
            </button>
          ) : null}
          <button className="btn btn-secondary" onClick={props.onClose} type="button">
            {UI_COPY.worldbook.close}
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-4">
        <div className="surface p-4">
          <WorldBookPreviewPanel {...props.previewPanelProps} variant="drawer" />
        </div>

        <label className="grid gap-1">
          <span className="text-xs text-subtext">{UI_COPY.worldbook.formTitle}</span>
          <input
            id="worldbook_entry_title"
            className="input"
            disabled={props.saving}
            name="title"
            value={props.form.title}
            onChange={(event) => props.onUpdateForm({ title: event.target.value })}
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex items-center justify-between gap-2 text-sm text-ink">
            <span>{UI_COPY.worldbook.formEnabled}</span>
            <input
              id="worldbook_entry_enabled"
              className="checkbox"
              checked={props.form.enabled}
              disabled={props.saving}
              name="enabled"
              onChange={(event) => props.onUpdateForm({ enabled: event.target.checked })}
              type="checkbox"
            />
          </label>
          <label className="flex items-center justify-between gap-2 text-sm text-ink">
            <span>{UI_COPY.worldbook.formConstant}</span>
            <input
              id="worldbook_entry_constant"
              className="checkbox"
              checked={props.form.constant}
              disabled={props.saving}
              name="constant"
              onChange={(event) => props.onUpdateForm({ constant: event.target.checked })}
              type="checkbox"
            />
          </label>
          <label className="flex items-center justify-between gap-2 text-sm text-ink">
            <span>{UI_COPY.worldbook.formExcludeRecursion}</span>
            <input
              id="worldbook_entry_exclude_recursion"
              className="checkbox"
              checked={props.form.exclude_recursion}
              disabled={props.saving}
              name="exclude_recursion"
              onChange={(event) => props.onUpdateForm({ exclude_recursion: event.target.checked })}
              type="checkbox"
            />
          </label>
          <label className="flex items-center justify-between gap-2 text-sm text-ink">
            <span>{UI_COPY.worldbook.formPreventRecursion}</span>
            <input
              id="worldbook_entry_prevent_recursion"
              className="checkbox"
              checked={props.form.prevent_recursion}
              disabled={props.saving}
              name="prevent_recursion"
              onChange={(event) => props.onUpdateForm({ prevent_recursion: event.target.checked })}
              type="checkbox"
            />
          </label>
          <label className="grid gap-1 sm:col-span-2">
            <span className="text-xs text-subtext">{UI_COPY.worldbook.formKeywords}</span>
            <textarea
              id="worldbook_entry_keywords"
              className="textarea atelier-content"
              disabled={props.saving}
              name="keywords"
              rows={2}
              value={props.form.keywords_raw}
              onChange={(event) => props.onUpdateForm({ keywords_raw: event.target.value })}
            />
            <div className="text-[11px] text-subtext">{UI_COPY.worldbook.formKeywordsHint}</div>
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">{UI_COPY.worldbook.formCharLimit}</span>
            <input
              id="worldbook_entry_char_limit"
              className="input"
              disabled={props.saving}
              min={0}
              name="char_limit"
              type="number"
              value={props.form.char_limit}
              onChange={(event) => props.onUpdateForm({ char_limit: event.currentTarget.valueAsNumber })}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">{UI_COPY.worldbook.formPriority}</span>
            <select
              id="worldbook_entry_priority"
              className="select"
              disabled={props.saving}
              name="priority"
              value={props.form.priority}
              onChange={(event) => props.onUpdateForm({ priority: event.target.value as WorldBookPriority })}
            >
              {WORLDBOOK_COPY.priorityOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.value}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="grid gap-1">
          <span className="text-xs text-subtext">{UI_COPY.worldbook.formContent}</span>
          <textarea
            id="worldbook_entry_content_md"
            className="textarea atelier-content"
            disabled={props.saving}
            name="content_md"
            rows={10}
            value={props.form.content_md}
            onChange={(event) => props.onUpdateForm({ content_md: event.target.value })}
          />
        </label>

        <div className="flex items-center justify-end gap-2">
          <button className="btn btn-secondary" disabled={props.saving} onClick={props.onClose} type="button">
            {UI_COPY.worldbook.cancel}
          </button>
          <button
            className="btn btn-primary"
            disabled={props.saving || !props.dirty}
            onClick={props.onSave}
            type="button"
          >
            {props.saving ? UI_COPY.worldbook.saving : UI_COPY.worldbook.save}
          </button>
        </div>
      </div>
    </Drawer>
  );
}
