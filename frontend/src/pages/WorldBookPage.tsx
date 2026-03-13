import {
  WorldBookAutoUpdateSection,
  WorldBookEditorDrawer,
  WorldBookEntriesSection,
  WorldBookImportDrawer,
  WorldBookPageActionsBar,
  WorldBookPreviewPanel,
} from "./worldbook/WorldBookPageSections";
import { useWorldBookPageState } from "./worldbook/useWorldBookPageState";

export function WorldBookPage() {
  const state = useWorldBookPageState();

  return (
    <div className="grid gap-4">
      <WorldBookPageActionsBar {...state.actionsBarProps} />
      <WorldBookAutoUpdateSection {...state.autoUpdateSectionProps} />

      <div className="grid gap-4 lg:grid-cols-2">
        <WorldBookEntriesSection {...state.entriesSectionProps} />
        <div className="panel p-4">
          <WorldBookPreviewPanel {...state.pagePreviewPanelProps} />
        </div>
      </div>

      <WorldBookImportDrawer {...state.importDrawerProps} />
      <WorldBookEditorDrawer {...state.editorDrawerProps} />
    </div>
  );
}
